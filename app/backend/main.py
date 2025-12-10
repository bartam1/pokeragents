"""
Poker POC - Main runner for tournament experiments.

This POC proves that agents with pre-loaded historical knowledge (Agent D)
outperform agents who must learn from scratch (Agent E).

Usage:
    uv run python -m backend.main --tournaments 5
"""
import argparse
import asyncio
import json
import signal
from collections import Counter
from datetime import datetime
from pathlib import Path

from backend.config import Settings
from backend.domain.tournament.orchestrator import (
    TournamentOrchestrator,
    TournamentConfig,
    TournamentResult,
)
from backend.domain.agent.utils import deviation_tracker
from backend.domain.player.recalculator import recalculate_baseline_stats
from backend.logging_config import setup_logging, get_logger, log_collector

logger = get_logger(__name__)

# Global state for graceful shutdown
_shutdown_requested = False
_current_orchestrator: TournamentOrchestrator | None = None


def _handle_sigint(signum, frame):
    """Handle SIGINT (Ctrl+C) for graceful shutdown."""
    global _shutdown_requested
    if _shutdown_requested:
        print("\n⚠️ Force quit - exiting immediately")
        raise SystemExit(1)
    
    _shutdown_requested = True
    print("\n⚠️ Shutdown requested - saving current tournament state...")
    
    if _current_orchestrator is not None:
        _current_orchestrator.save_incomplete()
    
    raise KeyboardInterrupt


async def run_single_tournament(
    settings: Settings,
    config: TournamentConfig,
    calibration_mode: bool = False,
) -> TournamentResult:
    """Run a single tournament and return results."""
    global _current_orchestrator
    
    orchestrator = TournamentOrchestrator(settings)
    _current_orchestrator = orchestrator
    
    orchestrator.setup_tournament(config=config, calibration_mode=calibration_mode)
    try:
        return await orchestrator.run_tournament()
    finally:
        _current_orchestrator = None


async def run_experiment(
    num_tournaments: int = 5,
    settings: Settings | None = None,
    calibration_mode: bool = False,
) -> dict:
    """
    Run multiple tournaments to compare Agent D vs Agent E performance.

    This is the main POC experiment that proves the hypothesis:
    Shared knowledge (Agent D) outperforms learning from scratch (Agent E).

    Args:
        num_tournaments: Number of tournaments to run
        settings: Application settings

    Returns:
        Dict with experiment results and statistics
    """
    settings = settings or Settings()
    
    # Reset deviation tracker for fresh stats
    deviation_tracker.reset()

    results = {
        "tournaments_run": 0,
        "agent_d_wins": 0,
        "agent_e_wins": 0,
        "agent_d_placements": [],
        "agent_e_placements": [],
        "all_placements": Counter(),
        "tournament_results": [],
    }

    config = TournamentConfig(
        starting_stack=1500,
        small_blind=10,
        big_blind=20,
        blind_increase_interval=15,
        max_hands=300,
    )

    for i in range(num_tournaments):
        logger.info(f"\n{'='*60}")
        logger.info(f"TOURNAMENT {i + 1}/{num_tournaments}")
        logger.info(f"{'='*60}\n")

        try:
            result = await run_single_tournament(settings, config, calibration_mode)

            results["tournaments_run"] += 1
            results["tournament_results"].append(result)

            # Track placements
            results["agent_d_placements"].append(result.agent_d_placement)
            results["agent_e_placements"].append(result.agent_e_placement)

            if result.agent_d_placement == 1:
                results["agent_d_wins"] += 1
            if result.agent_e_placement == 1:
                results["agent_e_wins"] += 1

            # Track all placements
            for idx, player_id in enumerate(result.placements):
                results["all_placements"][(player_id, idx + 1)] += 1

            logger.info(
                f"Tournament {i + 1} complete. "
                f"D placed: {result.agent_d_placement}, "
                f"E placed: {result.agent_e_placement}"
            )

        except Exception as e:
            logger.error(f"Tournament {i + 1} failed: {e}")
            continue

    # Calculate statistics
    if results["agent_d_placements"]:
        results["agent_d_avg_placement"] = (
            sum(results["agent_d_placements"]) / len(results["agent_d_placements"])
        )
    else:
        results["agent_d_avg_placement"] = 0

    if results["agent_e_placements"]:
        results["agent_e_avg_placement"] = (
            sum(results["agent_e_placements"]) / len(results["agent_e_placements"])
        )
    else:
        results["agent_e_avg_placement"] = 0

    if results["tournaments_run"] > 0:
        results["agent_d_win_rate"] = results["agent_d_wins"] / results["tournaments_run"]
        results["agent_e_win_rate"] = results["agent_e_wins"] / results["tournaments_run"]
    else:
        results["agent_d_win_rate"] = 0
        results["agent_e_win_rate"] = 0
    
    # Add GTO deviation statistics
    results["gto_deviation_stats"] = deviation_tracker.to_dict()

    return results


def save_experiment_results(results: dict, output_dir: str = "data/results", include_logs: bool = True) -> str:
    """Save experiment results to JSON file with timestamp.
    
    Args:
        results: Experiment results dict
        output_dir: Directory to save results
        include_logs: Whether to include game logs in output
        
    Returns:
        Path to saved results file
    """
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = path / f"experiment_{timestamp}.json"
    
    # Prepare serializable data
    export_data = {
        "timestamp": timestamp,
        "tournaments_run": results["tournaments_run"],
        "agent_d": {
            "wins": results["agent_d_wins"],
            "win_rate": results["agent_d_win_rate"],
            "avg_placement": results["agent_d_avg_placement"],
            "placements": results["agent_d_placements"],
        },
        "agent_e": {
            "wins": results["agent_e_wins"],
            "win_rate": results["agent_e_win_rate"],
            "avg_placement": results["agent_e_avg_placement"],
            "placements": results["agent_e_placements"],
        },
        "all_placements": {
            f"{player}_{place}": count 
            for (player, place), count in results["all_placements"].items()
        },
        "tournament_details": [
            {
                "tournament_num": i + 1,
                "placements": r.placements,
                "agent_d_placement": r.agent_d_placement,
                "agent_e_placement": r.agent_e_placement,
                "hands_played": r.hand_count,
                "final_stacks": r.final_stacks,
            }
            for i, r in enumerate(results.get("tournament_results", []))
        ],
        "hypothesis_confirmed": results["agent_d_avg_placement"] < results["agent_e_avg_placement"],
        "gto_deviation_stats": results.get("gto_deviation_stats", {}),
    }
    
    # Include game logs if requested
    if include_logs:
        export_data["game_logs"] = log_collector.get_entries()
    
    with open(filename, "w") as f:
        json.dump(export_data, f, indent=2)
    
    return str(filename)


def print_results(results: dict) -> None:
    """Print experiment results in a nice format."""
    print("\n" + "=" * 70)
    print("🃏 POKER POC EXPERIMENT RESULTS")
    print("=" * 70)
    print(f"Tournaments completed: {results['tournaments_run']}")
    print()

    print("AGENT D (Simple Architecture - Single LLM):")
    print(f"  - Wins: {results['agent_d_wins']}")
    print(f"  - Win Rate: {results['agent_d_win_rate']:.1%}")
    print(f"  - Average Placement: {results['agent_d_avg_placement']:.2f}")
    print(f"  - Placements: {results['agent_d_placements']}")
    print()

    print("AGENT E (Ensemble Architecture - GTO + Exploit + Decision):")
    print(f"  - Wins: {results['agent_e_wins']}")
    print(f"  - Win Rate: {results['agent_e_win_rate']:.1%}")
    print(f"  - Average Placement: {results['agent_e_avg_placement']:.2f}")
    print(f"  - Placements: {results['agent_e_placements']}")
    print()

    print("ALL AGENT PLACEMENT DISTRIBUTION:")
    for (player_id, placement), count in sorted(results["all_placements"].items()):
        print(f"  - {player_id} placed {placement}: {count} times")
    print()
    
    # Print GTO deviation stats
    deviation_stats = results.get("gto_deviation_stats", {})
    if deviation_stats:
        print("=" * 70)
        print("📐 GTO DEVIATION ANALYSIS:")
        print("=" * 70)
        
        summary = deviation_stats.get("summary", {})
        total_gto = summary.get("total_gto_decisions", 0)
        total_dev = summary.get("total_deviation_decisions", 0)
        dev_rate = summary.get("overall_deviation_rate", 0)
        gto_profit = summary.get("total_gto_profit", 0)
        dev_profit = summary.get("total_deviation_profit", 0)
        
        print(f"Overall:")
        print(f"  - GTO Decisions: {total_gto}")
        print(f"  - Deviation Decisions: {total_dev}")
        print(f"  - Deviation Rate: {dev_rate:.1%}")
        print(f"  - GTO Profit/Loss: {gto_profit:+.0f}")
        print(f"  - Deviation Profit/Loss: {dev_profit:+.0f}")
        print()
        
        by_agent = deviation_stats.get("by_agent", {})
        for agent_id in ["agent_d", "agent_e"]:
            if agent_id in by_agent:
                stats = by_agent[agent_id]
                gto_count = stats.get("gto_decisions", 0)
                dev_count = stats.get("deviation_decisions", 0)
                rate = stats.get("deviation_rate", 0)
                gto_p = stats.get("gto_profit", 0)
                dev_p = stats.get("deviation_profit", 0)
                gto_avg = stats.get("gto_avg_profit", 0)
                dev_avg = stats.get("deviation_avg_profit", 0)
                
                agent_label = "Agent D (Simple)" if agent_id == "agent_d" else "Agent E (Ensemble)"
                print(f"{agent_label}:")
                print(f"  - Decisions: {gto_count} GTO, {dev_count} deviations ({rate:.1%} deviation rate)")
                print(f"  - GTO Profit: {gto_p:+.0f} (avg: {gto_avg:+.1f}/hand)")
                print(f"  - Deviation Profit: {dev_p:+.0f} (avg: {dev_avg:+.1f}/hand)")
                
                # Verdict
                if dev_count > 0 and gto_count > 0:
                    if dev_avg > gto_avg:
                        print(f"  ✅ Deviations were PROFITABLE (avg +{dev_avg - gto_avg:.1f}/hand better)")
                    else:
                        print(f"  ❌ Deviations were COSTLY (avg {dev_avg - gto_avg:.1f}/hand worse)")
                print()

    print("=" * 70)
    print("CONCLUSION:")
    print("=" * 70)

    if results["agent_d_avg_placement"] < results["agent_e_avg_placement"]:
        improvement = (
            (results["agent_e_avg_placement"] - results["agent_d_avg_placement"])
            / results["agent_e_avg_placement"]
            * 100
        )
        print(f"✅ SIMPLE ARCHITECTURE WINS!")
        print(f"   Agent D (single LLM) performs {improvement:.1f}% better")
        print(f"   than Agent E (ensemble).")
        print()
        print("   Combined GTO+Exploit in one prompt may be more efficient")
        print("   than separating into specialized agents.")
    elif results["agent_d_avg_placement"] > results["agent_e_avg_placement"]:
        improvement = (
            (results["agent_d_avg_placement"] - results["agent_e_avg_placement"])
            / results["agent_d_avg_placement"]
            * 100
        )
        print(f"✅ ENSEMBLE ARCHITECTURE WINS!")
        print(f"   Agent E (GTO + Exploit + Decision) performs {improvement:.1f}% better")
        print(f"   than Agent D (single LLM).")
        print()
        print("   Separating analysis into specialized agents provides")
        print("   better decision quality despite higher latency.")
    else:
        print("⚖️ INCONCLUSIVE")
        print("   Both architectures performed similarly.")
        print("   More tournaments may be needed for statistical significance.")

    print("=" * 70)


def main():
    """Main entry point."""
    global _shutdown_requested
    
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, _handle_sigint)
    
    parser = argparse.ArgumentParser(
        description="Poker POC - AI Agents with Shared Knowledge Experiment"
    )
    parser.add_argument(
        "-n", "--tournaments",
        type=int,
        default=3,
        help="Number of tournaments to run (default: 3)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "-c", "--calibrate",
        action="store_true",
        help="Run in calibration mode to learn real agent behaviors",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level)

    # Load settings
    try:
        settings = Settings()
        # Configure OpenAI client with environment variables
        settings.configure_openai_client()
    except Exception as e:
        print(f"Error loading settings: {e}")
        print("Make sure you have a .env file with OPENAI_API_KEY set.")
        return

    # Run experiment
    if args.calibrate:
        print(f"\n🔧 Running CALIBRATION MODE with {args.tournaments} tournaments...\n")
        print("   Agent D will start fresh and learn real opponent behaviors.\n")
    else:
        print(f"\n🎲 Starting Poker POC Experiment with {args.tournaments} tournaments...\n")
        
        # Recalculate baseline statistics from saved game states
        calibrated_path = f"{settings.knowledge_persistence_dir}/calibrated_stats.json"
        baseline_kb = recalculate_baseline_stats(
            gamestates_dir=settings.gamestates_dir,
            output_path=calibrated_path,
        )
        if baseline_kb.profiles:
            print(f"📊 Recalculated baseline stats from {baseline_kb.get_total_hands_observed()} total hands\n")

    try:
        results = asyncio.run(run_experiment(
            num_tournaments=args.tournaments,
            settings=settings,
            calibration_mode=args.calibrate,
        ))

        # Print results
        print_results(results)
        
        if args.calibrate:
            print("\n🔧 Calibration complete! Run without --calibrate to use learned stats.")

        # Save results to file
        results_file = save_experiment_results(results)
        print(f"\n📊 Results saved to: {results_file}")
        
    except KeyboardInterrupt:
        print("\n⚠️ Experiment interrupted. Partial results may have been saved.")
        if _shutdown_requested:
            print("   Incomplete tournament data saved with 'incomplete_' prefix.")


if __name__ == "__main__":
    main()



