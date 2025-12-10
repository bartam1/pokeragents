import { useState, useMemo } from 'react';
import FileUploader from './components/FileUploader';
import PlayerSelector from './components/PlayerSelector';
import ChipGraph from './components/ChipGraph';
import './App.css';

function App() {
  const [tournamentData, setTournamentData] = useState([]);
  const [selectedPlayers, setSelectedPlayers] = useState([]);

  const handleFilesLoaded = (data) => {
    setTournamentData(data);
    // Auto-select all players when new files are loaded
    const allPlayers = new Set();
    data.forEach((fileData) => {
      fileData.tournaments.forEach((tournament) => {
        if (tournament.final_stacks) {
          Object.keys(tournament.final_stacks).forEach((player) => {
            allPlayers.add(player);
          });
        }
      });
    });
    setSelectedPlayers(Array.from(allPlayers));
  };

  // Extract all unique players from loaded data
  const allPlayers = useMemo(() => {
    const players = new Set();
    tournamentData.forEach((fileData) => {
      fileData.tournaments.forEach((tournament) => {
        if (tournament.final_stacks) {
          Object.keys(tournament.final_stacks).forEach((player) => {
            players.add(player);
          });
        }
      });
    });
    return Array.from(players).sort();
  }, [tournamentData]);

  return (
    <div className="app">
      <header className="app-header">
        <h1>🃏 Poker Tournament Chip Tracker</h1>
        <p className="subtitle">Visualize chip progression across tournaments</p>
      </header>

      <main className="app-main">
        <section className="upload-section">
          <FileUploader onFilesLoaded={handleFilesLoaded} />
        </section>

        {tournamentData.length > 0 && (
          <>
            <section className="controls-section">
              <PlayerSelector
                players={allPlayers}
                selectedPlayers={selectedPlayers}
                onSelectionChange={setSelectedPlayers}
              />
            </section>

            <section className="chart-section">
              <h2>Chip Progression</h2>
              <ChipGraph
                data={tournamentData}
                selectedPlayers={selectedPlayers}
              />
            </section>

            <section className="stats-section">
              <h2>Tournament Summary</h2>
              <div className="stats-grid">
                <div className="stat-card">
                  <span className="stat-value">{tournamentData.length}</span>
                  <span className="stat-label">Files Loaded</span>
                </div>
                <div className="stat-card">
                  <span className="stat-value">
                    {tournamentData.reduce((sum, f) => sum + f.tournaments.length, 0)}
                  </span>
                  <span className="stat-label">Total Tournaments</span>
                </div>
                <div className="stat-card">
                  <span className="stat-value">{allPlayers.length}</span>
                  <span className="stat-label">Unique Players</span>
                </div>
              </div>
            </section>
          </>
        )}
      </main>

      <footer className="app-footer">
        <p>Upload tournament JSON files to visualize chip changes</p>
      </footer>
    </div>
  );
}

export default App;
