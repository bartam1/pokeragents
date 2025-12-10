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
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

from backend.config import Settings
from backend.domain.agent.utils import deviation_tracker
from backend.domain.tournament.orchestrator import (
    TournamentConfig,
    TournamentOrchestrator,
    TournamentResult,
)
from backend.logging_config import get_logger, log_collector, setup_logging

logger = get_logger(__name__)


async def run_single_tournament(
    settings: Settings,
    config: TournamentConfig,
    calibration_mode: bool = False,
) -> TournamentResult:
    """Run a single tournament and return results."""
    orchestrator = TournamentOrchestrator(settings)
    orchestrator.setup_tournament(config=config, calibration_mode=calibration_mode)
    return await orchestrator.run_tournament()


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
        # EV tracking aggregates
        "ev_by_player": {},  # Accumulated EV across all tournaments
        "ev_records": [],  # All EV records
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

            # Aggregate EV data
            for player_id, ev_data in result.ev_by_player.items():
                if player_id not in results["ev_by_player"]:
                results["ev_by_player"][player_id] = {
                    "ev_chips": 0.0,
                    "actual_chips": 0.0,
                    "variance": 0.0,
                    "ev_adjusted": 0.0,
                    "showdown_count": 0,
                }
                results["ev_by_player"][player_id]["ev_chips"] += ev_data["ev_chips"]
                results["ev_by_player"][player_id]["actual_chips"] += ev_data["actual_chips"]
                results["ev_by_player"][player_id]["variance"] += ev_data["variance"]
                results["ev_by_player"][player_id]["ev_adjusted"] += ev_data["ev_adjusted"]
                results["ev_by_player"][player_id]["showdown_count"] += ev_data["showdown_count"]

            # Collect all EV records
            results["ev_records"].extend([r.to_dict() for r in result.ev_records])

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
        results["agent_d_avg_placement"] = sum(results["agent_d_placements"]) / len(
            results["agent_d_placements"]
        )
    else:
        results["agent_d_avg_placement"] = 0

    if results["agent_e_placements"]:
        results["agent_e_avg_placement"] = sum(results["agent_e_placements"]) / len(
            results["agent_e_placements"]
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


def save_experiment_results(
    results: dict, output_dir: str = "data/results", include_logs: bool = True
) -> str:
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

    # Get EV data for agents
    ev_by_player = results.get("ev_by_player", {})
    agent_d_ev = ev_by_player.get("agent_d", {})
    agent_e_ev = ev_by_player.get("agent_e", {})

    # Prepare serializable data
    export_data = {
        "timestamp": timestamp,
        "tournaments_run": results["tournaments_run"],
        "agent_d": {
            "wins": results["agent_d_wins"],
            "win_rate": results["agent_d_win_rate"],
            "avg_placement": results["agent_d_avg_placement"],
            "placements": results["agent_d_placements"],
            # EV tracking
            "ev_chips": agent_d_ev.get("ev_chips", 0),
            "actual_chips": agent_d_ev.get("actual_chips", 0),
            "variance": agent_d_ev.get("variance", 0),
            "ev_adjusted": agent_d_ev.get("ev_adjusted", 0),
            "showdown_count": agent_d_ev.get("showdown_count", 0),
        },
        "agent_e": {
            "wins": results["agent_e_wins"],
            "win_rate": results["agent_e_win_rate"],
            "avg_placement": results["agent_e_avg_placement"],
            "placements": results["agent_e_placements"],
            # EV tracking
            "ev_chips": agent_e_ev.get("ev_chips", 0),
            "actual_chips": agent_e_ev.get("actual_chips", 0),
            "variance": agent_e_ev.get("variance", 0),
            "ev_adjusted": agent_e_ev.get("ev_adjusted", 0),
            "showdown_count": agent_e_ev.get("showdown_count", 0),
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
                "ev_by_player": r.ev_by_player,
            }
            for i, r in enumerate(results.get("tournament_results", []))
        ],
        "hypothesis_confirmed": results["agent_d_avg_placement"] < results["agent_e_avg_placement"],
        "gto_deviation_stats": results.get("gto_deviation_stats", {}),
        # Include EV summary
        "ev_analysis": {
            "by_player": ev_by_player,
            "showdown_records": results.get("ev_records", []),
        },
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

        print("Overall:")
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
                print(
                    f"  - Decisions: {gto_count} GTO, {dev_count} deviations ({rate:.1%} deviation rate)"
                )
                print(f"  - GTO Profit: {gto_p:+.0f} (avg: {gto_avg:+.1f}/hand)")
                print(f"  - Deviation Profit: {dev_p:+.0f} (avg: {dev_avg:+.1f}/hand)")

                # Verdict
                if dev_count > 0 and gto_count > 0:
                    if dev_avg > gto_avg:
                        print(
                            f"  ✅ Deviations were PROFITABLE (avg +{dev_avg - gto_avg:.1f}/hand better)"
                        )
                    else:
                        print(
                            f"  ❌ Deviations were COSTLY (avg {dev_avg - gto_avg:.1f}/hand worse)"
                        )
                print()

    # Print EV analysis
    ev_by_player = results.get("ev_by_player", {})
    print("=" * 70)
    print("📈 EV ANALYSIS (Showdown Hands Only):")
    print("=" * 70)
    print("EV chips = expected result based on equity (luck removed)")
    print()

    # Get showdown counts for both agents
    agent_d_data = ev_by_player.get("agent_d", {})
    agent_e_data = ev_by_player.get("agent_e", {})
    agent_d_showdowns = agent_d_data.get("showdown_count", 0)
    agent_e_showdowns = agent_e_data.get("showdown_count", 0)

    for agent_id in ["agent_d", "agent_e"]:
        agent_label = "Agent D (Simple)" if agent_id == "agent_d" else "Agent E (Ensemble)"
        
        if agent_id in ev_by_player:
            ev_data = ev_by_player[agent_id]
            ev_chips = ev_data.get("ev_chips", 0)
            actual_chips = ev_data.get("actual_chips", 0)
            showdowns = ev_data.get("showdown_count", 0)

            print(f"{agent_label} ({showdowns} showdowns):")
            print(f"  - EV Chips:     {ev_chips:+.0f} (decision quality)")
            print(f"  - Actual Chips: {actual_chips:+.0f} (what happened)")
            print()
        else:
            # Agent had no showdowns
            print(f"{agent_label} (0 showdowns):")
            print("  - No showdown data (won/lost without showing cards)")
            print()

    # EV-adjusted comparison
    agent_d_ev = agent_d_data.get("ev_chips", 0)
    agent_e_ev = agent_e_data.get("ev_chips", 0)

    # Calculate EV-adjusted totals
    # Formula: EV-Adjusted Total = sum(ev_adjusted from showdowns) + non-showdown profit
    # This uses EV when available (showdowns), actual when not (non-showdowns)
    starting_stack = 1500  # Default starting stack
    
    # Get actual total profit/loss from final stacks
    tournament_results = results.get("tournament_results", [])
    
    # Calculate per-agent totals across all tournaments
    agent_d_actual_total = sum(
        r.final_stacks.get("agent_d", starting_stack) - starting_stack 
        for r in tournament_results
    )
    agent_e_actual_total = sum(
        r.final_stacks.get("agent_e", starting_stack) - starting_stack 
        for r in tournament_results
    )
    
    # Get showdown ev_adjusted and actual from ev_by_player
    agent_d_showdown_ev_adjusted = agent_d_data.get("ev_adjusted", 0)
    agent_d_showdown_actual = agent_d_data.get("actual_chips", 0)
    agent_e_showdown_ev_adjusted = agent_e_data.get("ev_adjusted", 0)
    agent_e_showdown_actual = agent_e_data.get("actual_chips", 0)
    
    # Non-showdown profit = actual_total - showdown_actual
    agent_d_non_showdown = agent_d_actual_total - agent_d_showdown_actual
    agent_e_non_showdown = agent_e_actual_total - agent_e_showdown_actual
    
    # EV-adjusted total = showdown_ev_adjusted + non_showdown_actual
    agent_d_ev_adjusted_total = agent_d_showdown_ev_adjusted + agent_d_non_showdown
    agent_e_ev_adjusted_total = agent_e_showdown_ev_adjusted + agent_e_non_showdown
    
    print("EV-Adjusted Total (EV for showdowns + actual for non-showdowns):")
    print(f"  Agent D: {agent_d_ev_adjusted_total:+.0f} chips")
    print(f"    └─ Showdown EV: {agent_d_showdown_ev_adjusted:+.0f} + Non-showdown: {agent_d_non_showdown:+.0f}")
    print(f"  Agent E: {agent_e_ev_adjusted_total:+.0f} chips")
    print(f"    └─ Showdown EV: {agent_e_showdown_ev_adjusted:+.0f} + Non-showdown: {agent_e_non_showdown:+.0f}")
    print()
    
    print("EV-Adjusted Comparison:")
    ev_adjusted_diff = agent_d_ev_adjusted_total - agent_e_ev_adjusted_total
    
    if agent_d_showdowns == 0 and agent_e_showdowns == 0:
        print("  ⚠️ No showdowns occurred - using actual chips only")
        print("  (Results are purely from non-showdown hands)")
    elif agent_d_showdowns == 0 or agent_e_showdowns == 0:
        missing = "D" if agent_d_showdowns == 0 else "E"
        print(f"  ⚠️ Agent {missing} had no showdowns - partial EV adjustment")
    
    if ev_adjusted_diff > 0:
        print(f"  ✅ Agent D outperformed Agent E by {ev_adjusted_diff:+.0f} EV-adjusted chips")
    elif ev_adjusted_diff < 0:
        print(f"  ✅ Agent E outperformed Agent D by {-ev_adjusted_diff:+.0f} EV-adjusted chips")
    else:
        print("  Both agents performed equally (EV-adjusted)")
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
        print("✅ SIMPLE ARCHITECTURE WINS!")
        print(f"   Agent D (single LLM) performs {improvement:.1f}% better")
        print("   than Agent E (ensemble).")
        print()
        print("   Combined GTO+Exploit in one prompt may be more efficient")
        print("   than separating into specialized agents.")
    elif results["agent_d_avg_placement"] > results["agent_e_avg_placement"]:
        improvement = (
            (results["agent_d_avg_placement"] - results["agent_e_avg_placement"])
            / results["agent_d_avg_placement"]
            * 100
        )
        print("✅ ENSEMBLE ARCHITECTURE WINS!")
        print(f"   Agent E (GTO + Exploit + Decision) performs {improvement:.1f}% better")
        print("   than Agent D (single LLM).")
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
    parser = argparse.ArgumentParser(
        description="Poker POC - AI Agents with Shared Knowledge Experiment"
    )
    parser.add_argument(
        "-n",
        "--tournaments",
        type=int,
        default=3,
        help="Number of tournaments to run (default: 3)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "-c",
        "--calibrate",
        action="store_true",
        help="Run in calibration mode to learn real agent behaviors",
    )

    args = parser.parse_args()

    # Setup logging - check env var first, then verbose flag
    log_level = os.environ.get("LOG_LEVEL", "DEBUG" if args.verbose else "INFO")
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

    results = asyncio.run(
        run_experiment(
            num_tournaments=args.tournaments,
            settings=settings,
            calibration_mode=args.calibrate,
        )
    )

    # Print results
    print_results(results)

    if args.calibrate:
        print("\n🔧 Calibration complete! Run without --calibrate to use learned stats.")

    # Save results to file
    results_file = save_experiment_results(results)
    print(f"\n📊 Results saved to: {results_file}")


if __name__ == "__main__":
    main()
