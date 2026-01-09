import { useState, useEffect, useMemo } from 'react';
import ChipGraph from './components/ChipGraph';
import './App.css';

function App() {
  const [availableFiles, setAvailableFiles] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [tournamentData, setTournamentData] = useState([]);
  const [selectedPlayers, setSelectedPlayers] = useState([]);
  const [useEV, setUseEV] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Load manifest on mount
  useEffect(() => {
    loadManifest();
  }, []);

  const loadManifest = async () => {
    try {
      setLoading(true);
      const res = await fetch('/gamestates/manifest.json');
      const manifest = await res.json();
      const files = manifest.files || [];
      setAvailableFiles(files);
      // Select last 5 files by default
      setSelectedFiles(files.slice(-5));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Load tournament data when selected files change
  useEffect(() => {
    if (selectedFiles.length === 0) {
      setTournamentData([]);
      return;
    }
    loadTournaments();
  }, [selectedFiles]);

  const loadTournaments = async () => {
    try {
      const allData = [];
      for (const filename of selectedFiles) {
        const res = await fetch(`/gamestates/${filename}`);
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
    }
  };

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

  const toggleFile = (filename) => {
    setSelectedFiles((prev) =>
      prev.includes(filename) ? prev.filter((f) => f !== filename) : [...prev, filename]
    );
  };

  const selectAllFiles = () => setSelectedFiles([...availableFiles]);
  const clearFiles = () => setSelectedFiles([]);
  const selectLast = (n) => setSelectedFiles(availableFiles.slice(-n));

  if (loading) {
    return <div className="app loading">Loading...</div>;
  }

  if (error) {
    return <div className="app error">Error: {error}</div>;
  }

  return (
    <div className="app">
      <header>
        <h1>🃏 Chip Tracker</h1>
        <div className="stats">
          <span>{selectedFiles.length}/{availableFiles.length} files</span>
          <span>{totalHands} hands</span>
          <span>{allPlayers.length} players</span>
        </div>
      </header>

      <div className="file-selector">
        <div className="file-actions">
          <span>Files:</span>
          <button onClick={() => selectLast(5)}>Last 5</button>
          <button onClick={() => selectLast(10)}>Last 10</button>
          <button onClick={selectAllFiles}>All</button>
          <button onClick={clearFiles}>Clear</button>
          <button onClick={loadManifest}>↻ Refresh</button>
        </div>
        <div className="file-list">
          {availableFiles.map((file) => (
            <label key={file} className={selectedFiles.includes(file) ? 'active' : ''}>
              <input
                type="checkbox"
                checked={selectedFiles.includes(file)}
                onChange={() => toggleFile(file)}
              />
              {file.replace('tournament_', '').replace('.json', '')}
            </label>
          ))}
        </div>
      </div>

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
