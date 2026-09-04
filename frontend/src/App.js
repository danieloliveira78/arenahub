import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import Landing from "@/pages/Landing";
import Competitions from "@/pages/Competitions";
import CompetitionDetail from "@/pages/CompetitionDetail";
import Dashboard from "@/pages/Dashboard";
import Admin from "@/pages/Admin";
import AdminCompetition from "@/pages/AdminCompetition";
import AuthCallback from "@/pages/AuthCallback";
import PaymentSuccess from "@/pages/PaymentSuccess";
import PaymentCancel from "@/pages/PaymentCancel";
import Ranking from "@/pages/Ranking";
import CheckIn from "@/pages/CheckIn";
import LiveSorteio from "@/pages/LiveSorteio";
import AthleteProfile from "@/pages/AthleteProfile";
import Financeiro from "@/pages/Financeiro";
import AdminUsers from "@/pages/AdminUsers";

function ProtectedRoute({ children, adminOnly = false }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen flex items-center justify-center text-slate-400">Carregando...</div>;
  if (!user) return <Navigate to="/" replace />;
  if (adminOnly && !user.is_admin) return <Navigate to="/dashboard" replace />;
  return children;
}

function AppRouter() {
  const location = useLocation();
  // Detect auth callback synchronously during render
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <>
      <Navbar />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/competicoes" element={<Competitions />} />
        <Route path="/competicoes/:id" element={<CompetitionDetail />} />
        <Route path="/ranking" element={<Ranking />} />
        <Route path="/atletas/:name" element={<AthleteProfile />} />
        <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
        <Route path="/admin" element={<ProtectedRoute adminOnly><Admin /></ProtectedRoute>} />
        <Route path="/admin/competicoes/:id" element={<ProtectedRoute adminOnly><AdminCompetition /></ProtectedRoute>} />
        <Route path="/admin/checkin" element={<ProtectedRoute adminOnly><CheckIn /></ProtectedRoute>} />
        <Route path="/admin/financeiro" element={<ProtectedRoute adminOnly><Financeiro /></ProtectedRoute>} />
        <Route path="/admin/usuarios" element={<ProtectedRoute adminOnly><AdminUsers /></ProtectedRoute>} />
        <Route path="/live/sorteio/:id" element={<ProtectedRoute adminOnly><LiveSorteio /></ProtectedRoute>} />
        <Route path="/payment/success" element={<PaymentSuccess />} />
        <Route path="/payment/cancel" element={<PaymentCancel />} />
      </Routes>
    </>
  );
}

function App() {
  return (
    <div className="App min-h-screen bg-[#0B0F17] text-slate-100">
      <BrowserRouter>
        <AuthProvider>
          <AppRouter />
          <Toaster theme="dark" position="top-right" richColors />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
