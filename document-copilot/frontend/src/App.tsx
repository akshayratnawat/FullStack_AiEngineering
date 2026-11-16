import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import AuthProvider from '@/components/auth/AuthProvider'
import ProtectedRoute from '@/components/auth/ProtectedRoute'
import ChatLayout from '@/components/chat/ChatLayout'
import ChatHomePage from '@/pages/ChatHomePage'
import ChatThreadPage from '@/pages/ChatThreadPage'
import LoginPage from '@/pages/LoginPage'
import SignUpPage from '@/pages/SignUpPage'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignUpPage />} />
          {/* Everything inside needs a signed-in user. */}
          <Route element={<ProtectedRoute />}>
            <Route element={<ChatLayout />}>
              <Route path="/" element={<ChatHomePage />} />
              <Route path="/chat/:threadId" element={<ChatThreadPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
