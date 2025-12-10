import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

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

export default function ChipGraph({ data, selectedPlayers }) {
  if (!data || data.length === 0) {
    return (
      <div className="chip-graph-empty">
        <p>No tournament data to display</p>
        <p className="hint">Upload tournament files to see the chip graph</p>
      </div>
    );
  }

  // Transform data for Recharts
  // Each data point: { tournament: "T1 (filename)", player1: chips, player2: chips, ... }
  const chartData = [];
  let tournamentIndex = 0;

  data.forEach((fileData) => {
    fileData.tournaments.forEach((tournament) => {
      tournamentIndex++;
      const point = {
        tournament: `T${tournamentIndex}`,
        tournamentNum: tournament.tournament_num,
        file: fileData.filename,
      };

      if (tournament.final_stacks) {
        Object.entries(tournament.final_stacks).forEach(([player, chips]) => {
          point[player] = chips;
        });
      }

      chartData.push(point);
    });
  });

  // Get all unique players from the data
  const allPlayers = new Set();
  chartData.forEach((point) => {
    Object.keys(point).forEach((key) => {
      if (key !== 'tournament' && key !== 'tournamentNum' && key !== 'file') {
        allPlayers.add(key);
      }
    });
  });

  // Filter to selected players
  const playersToShow = selectedPlayers.length > 0
    ? selectedPlayers.filter((p) => allPlayers.has(p))
    : Array.from(allPlayers);

  const getPlayerColor = (player, index) => {
    return PLAYER_COLORS[player] || DEFAULT_COLORS[index % DEFAULT_COLORS.length];
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const point = chartData.find((p) => p.tournament === label);
      return (
        <div className="custom-tooltip">
          <p className="tooltip-label">{label}</p>
          {point && <p className="tooltip-file">File: {point.file}</p>}
          {payload.map((entry, index) => (
            <p key={index} style={{ color: entry.color }}>
              {entry.name}: {entry.value?.toLocaleString() ?? 0} chips
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="chip-graph">
      <ResponsiveContainer width="100%" height={400}>
        <LineChart
          data={chartData}
          margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#444" />
          <XAxis
            dataKey="tournament"
            stroke="#888"
            tick={{ fill: '#ccc' }}
          />
          <YAxis
            stroke="#888"
            tick={{ fill: '#ccc' }}
            tickFormatter={(value) => value.toLocaleString()}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          {playersToShow.map((player, index) => (
            <Line
              key={player}
              type="monotone"
              dataKey={player}
              stroke={getPlayerColor(player, index)}
              strokeWidth={2}
              dot={{ fill: getPlayerColor(player, index), strokeWidth: 2, r: 4 }}
              activeDot={{ r: 6 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

