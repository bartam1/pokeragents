import { useState, useEffect, useMemo } from 'react';
import ChipGraph from './components/ChipGraph';
import './App.css';

function App() {
  const [tournamentData, setTournamentData] = useState([]);
  const [selectedPlayers, setSelectedPlayers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Load tournament data from static path on mount
  useEffect(() => {
    const loadTournaments = async () => {
      try {
        const manifestRes = await fetch('/results/manifest.json');
        const manifest = await manifestRes.json();

        const allData = [];
        for (const filename of manifest.files) {
          const res = await fetch(`/results/${filename}`);
          const data = await res.json();
          
          // Handle new format (format_version 3) with hand_summaries
          if (data.hand_summaries && Array.isArray(data.hand_summaries)) {
            // Get initial stacks from first hand
            const initialStacks = data.hands?.[0]?.starting_stacks || {};
            allData.push({
              filename,
              timestamp: data.timestamp,
              tournamentId: data.tournament_id,
              players: data.players || Object.keys(initialStacks),
              handSummaries: data.hand_summaries,
              initialStacks,
            });
          }
        }

        // Sort by timestamp
        allData.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
        setTournamentData(allData);

        // Auto-select all players
        const players = new Set();
        allData.forEach((file) => {
          file.players.forEach((p) => players.add(p));
        });
        setSelectedPlayers(Array.from(players));
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    loadTournaments();
  }, []);

  const allPlayers = useMemo(() => {
    const players = new Set();
    tournamentData.forEach((file) => {
      file.players.forEach((p) => players.add(p));
    });
    return Array.from(players).sort();
  }, [tournamentData]);

  const totalHands = useMemo(() => 
    tournamentData.reduce((sum, f) => sum + f.handSummaries.length, 0),
    [tournamentData]
  );

  const togglePlayer = (player) => {
    setSelectedPlayers((prev) =>
      prev.includes(player) ? prev.filter((p) => p !== player) : [...prev, player]
    );
  };

  if (loading) {
    return <div className="app loading">Loading tournaments...</div>;
  }

  if (error) {
    return <div className="app error">Error: {error}</div>;
  }

  return (
    <div className="app">
      <header>
        <h1>🃏 Chip Tracker</h1>
        <div className="stats">
          <span>{tournamentData.length} files</span>
          <span>{totalHands} hands</span>
          <span>{allPlayers.length} players</span>
        </div>
      </header>

      <div className="players">
        {allPlayers.map((player, i) => (
          <label key={player} className={selectedPlayers.includes(player) ? 'active' : ''}>
            <input
              type="checkbox"
              checked={selectedPlayers.includes(player)}
              onChange={() => togglePlayer(player)}
            />
            <span className="dot" data-player={i} />
            {player}
          </label>
        ))}
      </div>

      <ChipGraph data={tournamentData} selectedPlayers={selectedPlayers} />
    </div>
  );
}

export default App;
