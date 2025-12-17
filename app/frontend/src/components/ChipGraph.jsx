import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts';

const COLORS = ['#ff6b6b', '#4ecdc4', '#ffe66d', '#95e1d3', '#a29bfe', '#fab1a0', '#74b9ff'];

export default function ChipGraph({ data, selectedPlayers, useEV }) {
  if (!data?.length) {
    return <div className="chip-graph-empty">No data</div>;
  }

  const chartData = [];
  const allPlayers = new Set();
  let globalHandIndex = 0;

  // Data is already sorted by timestamp (ascending) in App.jsx
  // Running totals persist across all tournaments (no initialization from starting stacks)
  const runningTotals = {};

  data.forEach((file, fileIndex) => {
    // Initialize players to 0 if not seen before
    file.players.forEach((p) => {
      if (runningTotals[p] === undefined) {
        runningTotals[p] = 0;
      }
      allPlayers.add(p);
    });

    // Sort hand summaries by hand_number (ascending)
    const sortedHands = [...file.handSummaries].sort((a, b) => a.hand_number - b.hand_number);

    sortedHands.forEach((hand) => {
      globalHandIndex++;
      const chipsWon = hand.chips_won || {};
      const evAdjusted = hand.ev_adjusted_chips || {};
      const playersUsingEV = [];

      // Update running totals per player
      file.players.forEach((player) => {
        const hasEVForPlayer = useEV && evAdjusted[player] !== undefined && evAdjusted[player] !== null;
        const delta = hasEVForPlayer ? evAdjusted[player] : (chipsWon[player] || 0);
        
        runningTotals[player] += delta;
        
        if (hasEVForPlayer) {
          playersUsingEV.push(player);
        }
      });

      const point = {
        name: globalHandIndex,
        label: `T${fileIndex + 1}:H${hand.hand_number}`,
        handNumber: hand.hand_number,
        file: file.filename,
        tournamentId: file.tournamentId,
        timestamp: file.timestamp,
        playersUsingEV,
      };

      Object.entries(runningTotals).forEach(([player, chips]) => {
        point[player] = Math.round(chips * 100) / 100;
      });

      chartData.push(point);
    });
  });

  const playerList = Array.from(allPlayers).sort();
  const players = selectedPlayers.length 
    ? selectedPlayers.filter((p) => allPlayers.has(p)) 
    : playerList;

  // Calculate Y-axis domain to include negative values
  let minValue = 0;
  let maxValue = 0;
  chartData.forEach((point) => {
    players.forEach((p) => {
      if (point[p] !== undefined) {
        minValue = Math.min(minValue, point[p]);
        maxValue = Math.max(maxValue, point[p]);
      }
    });
  });
  // Add padding
  const padding = Math.max(100, (maxValue - minValue) * 0.1);
  const yMin = Math.floor((minValue - padding) / 100) * 100;
  const yMax = Math.ceil((maxValue + padding) / 100) * 100;

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    const pt = chartData.find((p) => p.name === label);
    return (
      <div className="custom-tooltip">
        <div className="tooltip-label">{pt?.label || `H${label}`}</div>
        {pt && <div className="tooltip-file">{pt.file}</div>}
        {payload.map((e, i) => {
          const isEV = pt?.playersUsingEV?.includes(e.name);
          return (
            <div key={i} style={{ color: e.color }}>
              {e.name}: {e.value?.toLocaleString()}{isEV ? ' (EV)' : ''}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="chip-graph">
      <ResponsiveContainer width="100%" height={350}>
        <LineChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
          <XAxis 
            dataKey="name" 
            stroke="#8b949e" 
            tick={{ fill: '#8b949e', fontSize: 11 }} 
          />
          <YAxis 
            stroke="#8b949e" 
            tick={{ fill: '#8b949e', fontSize: 11 }} 
            tickFormatter={(v) => v.toLocaleString()}
            domain={[yMin, yMax]}
          />
          {/* Zero reference line */}
          <ReferenceLine y={0} stroke="#666" strokeDasharray="3 3" />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {players.map((p) => (
            <Line
              key={p}
              type="monotone"
              dataKey={p}
              stroke={COLORS[playerList.indexOf(p) % COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
