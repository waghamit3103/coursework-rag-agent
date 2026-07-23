export default function SourceList({ sources }) {
  if (!sources || sources.length === 0) {
    return null;
  }

  return (
    <div className="source-list">
      <div className="source-list__label">Sources</div>
      <ul>
        {sources.map((source, i) => (
          <li key={i} className="source-list__item">
            <span className="source-list__score">{source.score.toFixed(2)}</span>
            <span className="source-list__citation">{source.citation}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
