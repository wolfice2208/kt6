/**
 * Защищённый маршрут.
 *
 * Проверка идёт на уровне роутера, а не «спрятать ссылку в меню»: если
 * неавторизованный пользователь введёт адрес руками, его перебросит на
 * /login, а исходный путь сохранится в state.from и восстановится после входа.
 */

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useIsAuthenticated } from "@/store/authStore";

interface PrivateRouteProps {
  children: ReactNode;
}

export function PrivateRoute({ children }: PrivateRouteProps): ReactNode {
  const isAuthenticated = useIsAuthenticated();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return <>{children}</>;
}
