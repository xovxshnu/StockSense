import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider, createBrowserRouter } from 'react-router-dom';
import AppRoutes from './routes/AppRoutes';
import './styles/global.css';

// A data router is required for useBlocker (unsaved-changes warning in forms).
const router = createBrowserRouter([{ path: '*', element: <AppRoutes /> }]);

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
