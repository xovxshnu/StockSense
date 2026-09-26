import { Routes, Route } from "react-router-dom";
import Home from "../pages/Home/Home.jsx";

// Feature branches add their routes here (Dashboard, Stock, Receipts, ...).
export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
    </Routes>
  );
}
