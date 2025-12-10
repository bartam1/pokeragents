const PLAYER_COLORS = {
  agent_a: '#ff6b6b',
  agent_b: '#4ecdc4',
  agent_c: '#ffe66d',
  agent_d: '#95e1d3',
  agent_e: '#a29bfe',
};

const DEFAULT_COLORS = [
  '#ff6b6b',
  '#4ecdc4',
  '#ffe66d',
  '#95e1d3',
  '#a29bfe',
  '#fab1a0',
  '#74b9ff',
  '#fd79a8',
  '#00b894',
  '#e17055',
];

export default function PlayerSelector({ players, selectedPlayers, onSelectionChange }) {
  if (!players || players.length === 0) {
    return null;
  }

  const getPlayerColor = (player, index) => {
    return PLAYER_COLORS[player] || DEFAULT_COLORS[index % DEFAULT_COLORS.length];
  };

  const handleToggle = (player) => {
    if (selectedPlayers.includes(player)) {
      onSelectionChange(selectedPlayers.filter((p) => p !== player));
    } else {
      onSelectionChange([...selectedPlayers, player]);
    }
  };

  const handleSelectAll = () => {
    onSelectionChange([...players]);
  };

  const handleSelectNone = () => {
    onSelectionChange([]);
  };

  return (
    <div className="player-selector">
      <div className="player-selector-header">
        <h3>Players</h3>
        <div className="player-selector-actions">
          <button onClick={handleSelectAll} className="action-btn">
            Select All
          </button>
          <button onClick={handleSelectNone} className="action-btn">
            Clear
          </button>
        </div>
      </div>
      <div className="player-list">
        {players.map((player, index) => (
          <label key={player} className="player-item">
            <input
              type="checkbox"
              checked={selectedPlayers.includes(player)}
              onChange={() => handleToggle(player)}
            />
            <span
              className="player-color"
              style={{ backgroundColor: getPlayerColor(player, index) }}
            />
            <span className="player-name">{player}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

