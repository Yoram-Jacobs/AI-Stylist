import '@/App.css';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from '@/components/ui/sonner';
import { AuthProvider } from '@/lib/auth';
import { AppLayout } from '@/components/AppLayout';
import { PublicOnly } from '@/components/PublicOnly';

import Login from '@/pages/Login';
import Register from '@/pages/Register';
import Home from '@/pages/Home';
import Closet from '@/pages/Closet';
import AddItem from '@/pages/AddItem';
import ItemDetail from '@/pages/ItemDetail';
import Stylist from '@/pages/Stylist';
import Marketplace from '@/pages/Marketplace';
import CreateListing from '@/pages/CreateListing';
import ListingDetail from '@/pages/ListingDetail';
import Profile from '@/pages/Profile';
import Transactions from '@/pages/Transactions';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<PublicOnly />}>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
          </Route>
          <Route element={<AppLayout />}>
            <Route path="/home" element={<Home />} />
            <Route path="/closet" element={<Closet />} />
            <Route path="/closet/add" element={<AddItem />} />
            <Route path="/closet/:id" element={<ItemDetail />} />
            <Route path="/stylist" element={<Stylist />} />
            <Route path="/market" element={<Marketplace />} />
            <Route path="/market/create" element={<CreateListing />} />
            <Route path="/market/:id" element={<ListingDetail />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/me" element={<Profile />} />
            <Route path="/" element={<Navigate to="/home" replace />} />
          </Route>
          <Route path="*" element={<Navigate to="/home" replace />} />
        </Routes>
        <Toaster position="top-center" richColors closeButton />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
