import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { TaskHistoryPage } from './pages/TaskHistoryPage';
import { TaskProgressPage } from './pages/TaskProgressPage';
import { UploadPage } from './pages/UploadPage';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<UploadPage />} />
        <Route path="/tasks" element={<TaskHistoryPage />} />
        <Route path="/tasks/:taskId" element={<TaskProgressPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
