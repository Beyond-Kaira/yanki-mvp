'use client'

import {
  createContext,
  useContext,
  useMemo,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from 'react'
import type { ShellSectionId } from '@/lib/shell-nav'

interface ShellStateValue {
  railHovered: boolean
  setRailHovered: Dispatch<SetStateAction<boolean>>
  hoveredSection: ShellSectionId | null
  setHoveredSection: Dispatch<SetStateAction<ShellSectionId | null>>
}

const ShellStateContext = createContext<ShellStateValue | null>(null)

export default function ShellStateProvider({
  children,
}: {
  children: ReactNode
}) {
  const [railHovered, setRailHovered] = useState(false)
  const [hoveredSection, setHoveredSection] = useState<ShellSectionId | null>(
    null,
  )
  const value = useMemo(
    () => ({ railHovered, setRailHovered, hoveredSection, setHoveredSection }),
    [hoveredSection, railHovered],
  )

  return (
    <ShellStateContext.Provider value={value}>
      {children}
    </ShellStateContext.Provider>
  )
}

export function useShellState(): ShellStateValue {
  const value = useContext(ShellStateContext)
  if (!value)
    throw new Error('useShellState must be used inside ShellStateProvider')
  return value
}
