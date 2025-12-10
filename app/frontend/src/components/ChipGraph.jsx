import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';

const COLORS = ['#ff6b6b', '#4ecdc4', '#ffe66d', '#95e1d3', '#a29bfe', '#fab1a0', '#74b9ff'];

export default function ChipGraph({ data, selectedPlayers }) {
  if (!data?.length) {
    return <div className="chip-graph-empty">No data</div>;
  }

  // Build chart data from hand_summaries
  // Calculate running chip totals per player
  const chartData = [];
  const allPlayers = new Set();

  data.forEach((file) => {
    // Initialize running totals from initial stacks (default 1500 if not available)
    const runningTotals = {};
    file.players.forEach((p) => {
      runningTotals[p] = file.initialStacks[p] ?? 1500;
      allPlayers.add(p);
    });

    // Process each hand
    file.handSummaries.forEach((hand) => {
      const handNum = hand.hand_number;
      
      // Use ev_adjusted_chips if available, otherwise use chips_won
      const chipsData = hand.ev_adjusted_chips || hand.chips_won;
      
      // Update running totals
      if (chipsData) {
        Object.entries(chipsData).forEach(([player, delta]) => {
          if (runningTotals[player] !== undefined) {
            runningTotals[player] += delta;
          }
        });
      }

      // Create data point
      const point = {
        name: `H${handNum}`,
        handNumber: handNum,
        file: file.filename,
        tournamentId: file.tournamentId,
        usedEV: !!hand.ev_adjusted_chips,
      };

      // Add each player's running total
      Object.entries(runningTotals).forEach(([player, chips]) => {
        point[player] = Math.round(chips * 100) / 100; // Round to 2 decimals
      });

      chartData.push(point);
    });
  });

  const playerList = Array.from(allPlayers).sort();
  const players = selectedPlayers.length 
    ? selectedPlayers.filter((p) => allPlayers.has(p)) 
    : playerList;

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    const pt = chartData.find((p) => p.name === label);
    return (
      <div className="custom-tooltip">
        <div className="tooltip-label">{label}</div>
        {pt && (
          <>
            <div className="tooltip-file">{pt.file}</div>
            {pt.usedEV && <div className="tooltip-ev">Using EV-adjusted chips</div>}
          </>
        )}
        {payload.map((e, i) => (
          <div key={i} style={{ color: e.color }}>
            {e.name}: {e.value?.toLocaleString()}
          </div>
        ))}
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
          />
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
