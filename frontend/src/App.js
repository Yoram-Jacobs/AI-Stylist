import '@/App.css';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import { Toaster } from '@/components/ui/sonner';
import { AuthProvider } from '@/lib/auth';
import { LocationProvider } from '@/lib/location';
import { PayPalProvider } from '@/lib/paypal';
import { AppLayout } from '@/components/AppLayout';
import { PublicOnly } from '@/components/PublicOnly';
import { SeoBase } from '@/components/SeoBase';

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
import Admin from '@/pages/Admin';
import ExpertsDirectory from '@/pages/ExpertsDirectory';
import AdsManager from '@/pages/AdsManager';

function App() {
  return (
    <HelmetProvider>
      <AuthProvider>
        <LocationProvider>
          <PayPalProvider>
            <BrowserRouter>
          <SeoBase />
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[1000] focus:bg-primary focus:text-primary-foreground focus:px-4 focus:py-2 focus:rounded-lg"
            data-testid="skip-to-content-link"
          >
            Skip to main content
          </a>
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
              <Route path="/admin" element={<Admin />} />
              <Route path="/experts" element={<ExpertsDirectory />} />
              <Route path="/ads" element={<AdsManager />} />
              <Route path="/me" element={<Profile />} />
              <Route path="/" element={<Navigate to="/home" replace />} />
            </Route>
            <Route path="*" element={<Navigate to="/home" replace />} />
          </Routes>
          <Toaster position="top-center" richColors closeButton />
          </BrowserRouter>
          </PayPalProvider>
        </LocationProvider>
      </AuthProvider>
    </HelmetProvider>
  );
}

export default App;
