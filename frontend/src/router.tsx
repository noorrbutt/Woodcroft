import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter, Navigate, useRouteError } from 'react-router-dom'

import { Layout } from '@/components/Layout'
import { Spinner } from '@/components/ui'
import { useAuthStore } from '@/features/auth/store'

/* Storefront pages that are part of the first meaningful paint stay eager.
   Everything else splits, and the whole admin tree is one lazy chunk so a
   shopper never downloads the charts and data tables. */
import { HomePage } from '@/routes/storefront/Home'
import { ShopPage } from '@/routes/storefront/Shop'
import { ProductPage } from '@/routes/storefront/Product'

const CartPage = lazy(() => import('@/routes/storefront/Cart'))
const CheckoutPage = lazy(() => import('@/routes/storefront/Checkout'))
const OrderConfirmationPage = lazy(() => import('@/routes/storefront/OrderConfirmation'))
const LoginPage = lazy(() => import('@/routes/storefront/Login'))
const RegisterPage = lazy(() => import('@/routes/storefront/Register'))
const ForgotPasswordPage = lazy(() => import('@/routes/storefront/ForgotPassword'))
const ResetPasswordPage = lazy(() => import('@/routes/storefront/ResetPassword'))
const VerifyEmailPage = lazy(() => import('@/routes/storefront/VerifyEmail'))
const AccountLayout = lazy(() => import('@/routes/storefront/account/AccountLayout'))
const AccountOverview = lazy(() => import('@/routes/storefront/account/Overview'))
const AccountOrders = lazy(() => import('@/routes/storefront/account/Orders'))
const AccountOrderDetail = lazy(() => import('@/routes/storefront/account/OrderDetail'))
const AccountAddresses = lazy(() => import('@/routes/storefront/account/Addresses'))
const AccountProfile = lazy(() => import('@/routes/storefront/account/Profile'))
const AccountWishlist = lazy(() => import('@/routes/storefront/account/Wishlist'))
const AccountSecurity = lazy(() => import('@/routes/storefront/account/Security'))
const ComparePage = lazy(() => import('@/routes/storefront/Compare'))
const JournalPage = lazy(() => import('@/routes/storefront/Journal'))
const JournalPostPage = lazy(() => import('@/routes/storefront/JournalPost'))
const StaticPage = lazy(() => import('@/routes/storefront/StaticPage'))
const FaqPage = lazy(() => import('@/routes/storefront/Faq'))
const ContactPage = lazy(() => import('@/routes/storefront/Contact'))

const AdminApp = lazy(() => import('@/routes/admin/AdminApp'))

function PageFallback() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <Spinner className="size-6 text-faint" />
    </div>
  )
}

function Boundary({ children }: { children: ReactNode }) {
  return <Suspense fallback={<PageFallback />}>{children}</Suspense>
}

function RequireAuth({ children }: { children: ReactNode }) {
  const user = useAuthStore((state) => state.user)
  const loading = useAuthStore((state) => state.loading)

  if (loading) return <PageFallback />
  if (!user) {
    const next = encodeURIComponent(window.location.pathname + window.location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  return <>{children}</>
}

function RequireStaff({ children }: { children: ReactNode }) {
  const user = useAuthStore((state) => state.user)
  const loading = useAuthStore((state) => state.loading)

  if (loading) return <PageFallback />
  if (!user) return <Navigate to="/login?next=/admin" replace />
  if (user.role !== 'admin' && user.role !== 'staff') {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

function ErrorPage() {
  const error = useRouteError() as { status?: number; message?: string }
  const notFound = error?.status === 404

  return (
    <div className="wc-container flex min-h-[60vh] flex-col items-center justify-center text-center">
      <p className="wc-numeral mb-4">{notFound ? '404' : 'ERROR'}</p>
      <h1 className="mb-4">
        {notFound ? 'We could not find that page' : 'Something went wrong'}
      </h1>
      <p className="mb-8 max-w-md text-sm text-muted">
        {notFound
          ? 'The page may have moved, or the link may be out of date.'
          : 'The page failed to load. Refreshing usually sorts it out.'}
      </p>
      <div className="flex gap-3">
        <a href="/" className="wc-btn wc-btn-primary">Back to home</a>
        <a href="/shop" className="wc-btn wc-btn-outline">Browse the shop</a>
      </div>
    </div>
  )
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    errorElement: <ErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'shop', element: <ShopPage /> },
      { path: 'search', element: <ShopPage /> },
      { path: 'collections/:slug', element: <ShopPage /> },
      { path: 'product/:slug', element: <ProductPage /> },
      { path: 'compare', element: <Boundary><ComparePage /></Boundary> },
      { path: 'cart', element: <Boundary><CartPage /></Boundary> },
      { path: 'checkout', element: <Boundary><CheckoutPage /></Boundary> },
      { path: 'order/:orderNumber', element: <Boundary><OrderConfirmationPage /></Boundary> },

      { path: 'login', element: <Boundary><LoginPage /></Boundary> },
      { path: 'register', element: <Boundary><RegisterPage /></Boundary> },
      { path: 'forgot-password', element: <Boundary><ForgotPasswordPage /></Boundary> },
      { path: 'reset-password', element: <Boundary><ResetPasswordPage /></Boundary> },
      { path: 'verify-email', element: <Boundary><VerifyEmailPage /></Boundary> },

      {
        path: 'account',
        element: (
          <RequireAuth>
            <Boundary><AccountLayout /></Boundary>
          </RequireAuth>
        ),
        children: [
          { index: true, element: <Boundary><AccountOverview /></Boundary> },
          { path: 'orders', element: <Boundary><AccountOrders /></Boundary> },
          { path: 'orders/:orderNumber', element: <Boundary><AccountOrderDetail /></Boundary> },
          { path: 'addresses', element: <Boundary><AccountAddresses /></Boundary> },
          { path: 'profile', element: <Boundary><AccountProfile /></Boundary> },
          { path: 'wishlist', element: <Boundary><AccountWishlist /></Boundary> },
          { path: 'security', element: <Boundary><AccountSecurity /></Boundary> },
        ],
      },

      { path: 'journal', element: <Boundary><JournalPage /></Boundary> },
      { path: 'journal/:slug', element: <Boundary><JournalPostPage /></Boundary> },
      { path: 'page/:slug', element: <Boundary><StaticPage /></Boundary> },
      { path: 'faq', element: <Boundary><FaqPage /></Boundary> },
      { path: 'contact', element: <Boundary><ContactPage /></Boundary> },

      { path: '*', element: <ErrorPage /> },
    ],
  },
  {
    path: '/admin/*',
    element: (
      <RequireStaff>
        <Boundary><AdminApp /></Boundary>
      </RequireStaff>
    ),
    errorElement: <ErrorPage />,
  },
])
