import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';

const COLORS = ['#ff6b6b', '#4ecdc4', '#ffe66d', '#95e1d3', '#a29bfe', '#fab1a0', '#74b9ff'];

export default function ChipGraph({ data, selectedPlayers, useEV }) {
  if (!data?.length) {
    return <div className="chip-graph-empty">No data</div>;
  }

  const chartData = [];
  const allPlayers = new Set();

  data.forEach((file) => {
    const runningTotals = {};
    file.players.forEach((p) => {
      runningTotals[p] = file.initialStacks[p] ?? 1500;
      allPlayers.add(p);
    });

    file.handSummaries.forEach((hand) => {
      const handNum = hand.hand_number;
      const chipsWon = hand.chips_won || {};
      const evAdjusted = hand.ev_adjusted_chips || {};

      // Track which players used EV in this hand
      const playersUsingEV = [];

      // Update running totals per player
      file.players.forEach((player) => {
        // Use ev_adjusted_chips if: checkbox is checked AND player has ev_adjusted value
        const hasEVForPlayer = useEV && evAdjusted[player] !== undefined && evAdjusted[player] !== null;
        const delta = hasEVForPlayer ? evAdjusted[player] : (chipsWon[player] || 0);
        
        runningTotals[player] += delta;
        
        if (hasEVForPlayer) {
          playersUsingEV.push(player);
        }
      });

      const point = {
        name: `H${handNum}`,
        handNumber: handNum,
        file: file.filename,
        tournamentId: file.tournamentId,
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

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    const pt = chartData.find((p) => p.name === label);
    return (
      <div className="custom-tooltip">
        <div className="tooltip-label">{label}</div>
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
          <XAxis dataKey="name" stroke="#8b949e" tick={{ fill: '#8b949e', fontSize: 11 }} />
          <YAxis stroke="#8b949e" tick={{ fill: '#8b949e', fontSize: 11 }} tickFormatter={(v) => v.toLocaleString()} />
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
