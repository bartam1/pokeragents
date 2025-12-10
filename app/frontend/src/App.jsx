import { useState, useEffect, useMemo } from 'react';
import ChipGraph from './components/ChipGraph';
import './App.css';

function App() {
  const [tournamentData, setTournamentData] = useState([]);
  const [selectedPlayers, setSelectedPlayers] = useState([]);
  const [useEV, setUseEV] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadTournaments = async () => {
      try {
        const manifestRes = await fetch('/results/manifest.json');
        const manifest = await manifestRes.json();

        const allData = [];
        for (const filename of manifest.files) {
          const res = await fetch(`/results/${filename}`);
          const data = await res.json();
          
          if (data.hand_summaries && Array.isArray(data.hand_summaries)) {
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

        allData.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
        setTournamentData(allData);

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

      <div className="controls">
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
        <label className={`ev-toggle ${useEV ? 'active' : ''}`}>
          <input
            type="checkbox"
            checked={useEV}
            onChange={(e) => setUseEV(e.target.checked)}
          />
          Use EV-adjusted chips
        </label>
      </div>

      <ChipGraph data={tournamentData} selectedPlayers={selectedPlayers} useEV={useEV} />
    </div>
  );
}

export default App;
