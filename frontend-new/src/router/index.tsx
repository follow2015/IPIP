/**
 * RouterProvider 配置
 * - 使用 createBrowserRouter 创建路由
 */
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { routes } from './routes';

export const router = createBrowserRouter(routes);

export function AppRouter() {
  return <RouterProvider router={router} />;
}

export default AppRouter;
