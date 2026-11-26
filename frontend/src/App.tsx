import { APP_BASE } from "@/lib/base";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { NotFoundPage } from "@/pages/NotFound";
import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { AuthenticatedRoute } from "@/auth/AuthenticatedRoute";
import { HomePage } from "@/pages/Home";
import { LoginPage } from "@/pages/Login";
import { SignupPage } from "@/pages/Signup";
import { ForgotPasswordPage } from "@/pages/ForgotPassword";
import { ResetPasswordPage } from "@/pages/ResetPassword";
import { VerifyEmailPage } from "@/pages/VerifyEmail";
import { AccountPage } from "@/pages/Account";
import { OwnerLayout } from "@/pages/owner/OwnerLayout";
import { OwnerDashboardPage } from "@/pages/owner/Dashboard";
import { OwnerProjectNewPage } from "@/pages/owner/ProjectNew";
import { OwnerProjectDetailPage } from "@/pages/owner/ProjectDetail";
import { OwnerVerifyPage } from "@/pages/owner/Verify";
import { OwnerStatusPage } from "@/pages/owner/Status";
import { ContractorLayout } from "@/pages/contractor/ContractorLayout";
import { ContractorDashboardPage } from "@/pages/contractor/Dashboard";
import { ContractorFeedPage } from "@/pages/contractor/Feed";
import { ContractorVerifyPage } from "@/pages/contractor/Verify";
import { ContractorStatusPage } from "@/pages/contractor/Status";
import { ContractorOfferPage } from "@/pages/contractor/Offer";
import { ContractorSubscribePage } from "@/pages/contractor/Subscribe";
import { ContractorSignupPage } from "@/pages/contractor/SignupWithCode";
import { ContractorJoinPage } from "@/pages/contractor/Join";
import { ContractorOnboardingPage } from "@/pages/contractor/Onboarding";
import { AdminLayout } from "@/pages/admin/AdminLayout";
import { AdminRequirementsPage } from "@/pages/admin/Requirements";
import { AdminReviewPage } from "@/pages/admin/Review";
import { AdminContractorsPage } from "@/pages/admin/Contractors";
import { AdminContractorDetailPage } from "@/pages/admin/ContractorDetail";
import { AdminOwnersPage } from "@/pages/admin/Owners";
import { AdminOwnerDetailPage } from "@/pages/admin/OwnerDetail";
import { AdminOffersPage } from "@/pages/admin/Offers";
import { AdminProjectsPage } from "@/pages/admin/Projects";
import { AdminProjectDetailPage } from "@/pages/admin/ProjectDetail";
import { AdminCmsPage } from "@/pages/admin/Cms";
import { AdminUserHistoryPage } from "@/pages/admin/UserHistory";
import { AdminPlansPage } from "@/pages/admin/Plans";
import { AdminPaymentSetupPage } from "@/pages/admin/PaymentSetup";
import { AdminUsersPage, AdminUserDetailPage } from "@/pages/admin/Users";
import {
  AdminActivationReportPage,
  AdminBillingReportPage,
  AdminReportsOverviewPage,
  AdminTenderReportPage,
} from "@/pages/admin/Reports";
import { AdminActivationsPage } from "@/pages/admin/Activations";

function AppRoutes() {
  const { pathname } = useLocation();
  return (
    <ErrorBoundary resetKey={pathname}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route
          path="/account"
          element={
            <AuthenticatedRoute>
              <AccountPage />
            </AuthenticatedRoute>
          }
        />

        <Route
          path="/owner/verify"
          element={
            <ProtectedRoute role="owner">
              <OwnerLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<OwnerVerifyPage />} />
        </Route>
        <Route
          path="/owner/status"
          element={
            <ProtectedRoute role="owner">
              <OwnerLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<OwnerStatusPage />} />
        </Route>
        <Route
          path="/owner"
          element={
            <ProtectedRoute role="owner" gate>
              <OwnerLayout />
            </ProtectedRoute>
          }
        >
          <Route path="dashboard" element={<OwnerDashboardPage />} />
          <Route path="projects/new" element={<OwnerProjectNewPage />} />
          <Route path="projects/:id" element={<OwnerProjectDetailPage />} />
        </Route>

        <Route
          path="/contractor/dashboard"
          element={
            <ProtectedRoute role="contractor">
              <ContractorLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<ContractorDashboardPage />} />
        </Route>
        <Route
          path="/contractor/verify"
          element={
            <ProtectedRoute role="contractor">
              <ContractorLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<ContractorVerifyPage />} />
        </Route>
        <Route
          path="/contractor/status"
          element={
            <ProtectedRoute role="contractor">
              <ContractorLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<ContractorStatusPage />} />
        </Route>
        <Route path="/contractor/signup" element={<ContractorSignupPage />} />
        <Route path="/contractor/join" element={<ContractorJoinPage />} />
        <Route
          path="/contractor/onboarding"
          element={
            <ProtectedRoute role="contractor">
              <ContractorLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<ContractorOnboardingPage />} />
        </Route>
        {/* Subscribing is open to any signed-up contractor: it is not behind the approval gate. */}
        <Route
          path="/contractor/subscribe"
          element={
            <ProtectedRoute role="contractor">
              <ContractorLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<ContractorSubscribePage />} />
        </Route>
        <Route
          path="/contractor"
          element={
            <ProtectedRoute role="contractor" gate>
              <ContractorLayout />
            </ProtectedRoute>
          }
        >
          <Route path="feed" element={<ContractorFeedPage />} />
          <Route path="projects/:id/offer" element={<ContractorOfferPage />} />
        </Route>

        <Route
          path="/admin"
          element={
            <ProtectedRoute role="admin">
              <AdminLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/admin/reports" replace />} />
          <Route path="reports" element={<AdminReportsOverviewPage />} />
          <Route path="reports/tenders" element={<AdminTenderReportPage />} />
          <Route path="reports/billing" element={<AdminBillingReportPage />} />
          <Route path="reports/activations" element={<AdminActivationReportPage />} />
          <Route path="users" element={<AdminUsersPage />} />
          <Route path="users/:id" element={<AdminUserDetailPage />} />
          <Route path="requirements" element={<AdminRequirementsPage />} />
          <Route path="review" element={<AdminReviewPage />} />
          <Route path="contractors" element={<AdminContractorsPage />} />
          <Route path="contractors/:id" element={<AdminContractorDetailPage />} />
          <Route path="owners" element={<AdminOwnersPage />} />
          <Route path="owners/:id" element={<AdminOwnerDetailPage />} />
          <Route path="offers" element={<AdminOffersPage />} />
          <Route path="projects" element={<AdminProjectsPage />} />
          <Route path="projects/:id" element={<AdminProjectDetailPage />} />
          <Route path="activations" element={<AdminActivationsPage />} />
          <Route path="plans" element={<AdminPlansPage />} />
          <Route path="payment-setup" element={<AdminPaymentSetupPage />} />
          <Route path="cms" element={<AdminCmsPage />} />
          <Route path="users/:userId/history" element={<AdminUserHistoryPage />} />
        </Route>

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </ErrorBoundary>
  );
}

export function App() {
  return (
    <BrowserRouter basename={APP_BASE || undefined}>
      <AppRoutes />
    </BrowserRouter>
  );
}
