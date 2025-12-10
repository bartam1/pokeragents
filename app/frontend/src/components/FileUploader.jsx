import { useState, useRef } from 'react';

export default function FileUploader({ onFilesLoaded }) {
  const [isDragging, setIsDragging] = useState(false);
  const [loadedFiles, setLoadedFiles] = useState([]);
  const fileInputRef = useRef(null);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files).filter(
      (file) => file.type === 'application/json' || file.name.endsWith('.json')
    );
    processFiles(files);
  };

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    processFiles(files);
  };

  const processFiles = async (files) => {
    const tournamentData = [];

    for (const file of files) {
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        
        if (data.tournament_details && Array.isArray(data.tournament_details)) {
          tournamentData.push({
            filename: file.name,
            timestamp: data.timestamp,
            tournaments: data.tournament_details,
          });
        }
      } catch (error) {
        console.error(`Error parsing ${file.name}:`, error);
      }
    }

    setLoadedFiles((prev) => [...prev, ...files.map((f) => f.name)]);
    onFilesLoaded(tournamentData);
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  const clearFiles = () => {
    setLoadedFiles([]);
    onFilesLoaded([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="file-uploader">
      <div
        className={`drop-zone ${isDragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          multiple
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />
        <div className="drop-zone-content">
          <span className="drop-icon">📁</span>
          <p>Drag & drop tournament JSON files here</p>
          <p className="drop-hint">or click to select files</p>
        </div>
      </div>

      {loadedFiles.length > 0 && (
        <div className="loaded-files">
          <div className="loaded-files-header">
            <span>Loaded files ({loadedFiles.length}):</span>
            <button onClick={clearFiles} className="clear-btn">
              Clear all
            </button>
          </div>
          <ul>
            {loadedFiles.map((name, index) => (
              <li key={index}>{name}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

