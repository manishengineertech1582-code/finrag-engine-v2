import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User } from '@supabase/supabase-js'

interface AuthState {
  user: User | null
  accessToken: string | null
  setSession: (user: User, accessToken: string) => void
  clearSession: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,

      setSession: (user, accessToken) => {
        localStorage.setItem('finrag_access_token', accessToken)
        set({ user, accessToken })
      },

      clearSession: () => {
        localStorage.removeItem('finrag_access_token')
        set({ user: null, accessToken: null })
      },
    }),
    {
      name: 'finrag-auth',
      partialize: (s) => ({ user: s.user, accessToken: s.accessToken }),
    }
  )
)
