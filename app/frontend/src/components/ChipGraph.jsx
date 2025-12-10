import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';

const COLORS = ['#ff6b6b', '#4ecdc4', '#ffe66d', '#95e1d3', '#a29bfe', '#fab1a0', '#74b9ff'];

export default function ChipGraph({ data, selectedPlayers }) {
  if (!data?.length) {
    return <div className="chip-graph-empty">No data</div>;
  }

  // Build chart data sorted by timestamp
  const chartData = [];
  let idx = 0;

  // Data is already sorted by timestamp in App.jsx
  data.forEach((file) => {
    file.tournaments.forEach((t) => {
      idx++;
      const point = { name: `T${idx}`, file: file.filename, ts: file.timestamp };
      if (t.final_stacks) {
        Object.entries(t.final_stacks).forEach(([p, chips]) => {
          point[p] = chips;
        });
      }
      chartData.push(point);
    });
  });

  const allPlayers = [...new Set(chartData.flatMap((p) => 
    Object.keys(p).filter((k) => !['name', 'file', 'ts'].includes(k))
  ))];

  const players = selectedPlayers.length ? selectedPlayers.filter((p) => allPlayers.includes(p)) : allPlayers;

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    const pt = chartData.find((p) => p.name === label);
    return (
      <div className="custom-tooltip">
        <div className="tooltip-label">{label}</div>
        {pt && <div className="tooltip-file">{pt.file}</div>}
        {payload.map((e, i) => (
          <div key={i} style={{ color: e.color }}>{e.name}: {e.value?.toLocaleString()}</div>
        ))}
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
          {players.map((p, i) => (
            <Line
              key={p}
              type="monotone"
              dataKey={p}
              stroke={COLORS[allPlayers.indexOf(p) % COLORS.length]}
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
