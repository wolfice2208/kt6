/**
 * Маршрутизация приложения.
 *
 * Восемь маршрутов: два динамических (/catalog/:itemId, /trades/:tradeId),
 * два защищённых через PrivateRoute (/trades, /trades/:tradeId) и страница 404.
 */

import { useEffect } from "react";
import { Route, Routes } from "react-router-dom";

import { AppLayout } from "@/components/AppLayout/AppLayout";
import { PrivateRoute } from "@/components/PrivateRoute";
import { CalculatorPage } from "@/pages/CalculatorPage/CalculatorPage";
import { CatalogPage } from "@/pages/CatalogPage/CatalogPage";
import { DashboardPage } from "@/pages/DashboardPage/DashboardPage";
import { ItemPage } from "@/pages/ItemPage/ItemPage";
import { LoginPage } from "@/pages/LoginPage/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage/NotFoundPage";
import { TradePage } from "@/pages/TradePage/TradePage";
import { TradesPage } from "@/pages/TradesPage/TradesPage";
import { useAuthStore } from "@/store/authStore";

export default function App() {
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);
  const syncUser = useAuthStore((state) => state.syncUser);

  // После перезагрузки страницы токен восстанавливается из localStorage,
  // а профиль мог не сохраниться — догружаем его по токену.
  useEffect(() => {
    if (token && !user) {
      void syncUser();
    }
  }, [token, user, syncUser]);

  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/catalog/:itemId" element={<ItemPage />} />
        <Route path="/calculator" element={<CalculatorPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/trades"
          element={
            <PrivateRoute>
              <TradesPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/trades/:tradeId"
          element={
            <PrivateRoute>
              <TradePage />
            </PrivateRoute>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppLayout>
  );
}
