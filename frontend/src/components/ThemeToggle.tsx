import { Moon, Sun, SunMoon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTheme, type Theme } from '@/hooks/useTheme'

const NEXT: Record<Theme, Theme> = { light: 'dark', dark: 'system', system: 'light' }
const ICON = { light: Sun, dark: Moon, system: SunMoon }
const LABEL = { light: 'Light', dark: 'Dark', system: 'System' }

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const Icon = ICON[theme]

  return (
    <Button
      variant="outline"
      size="icon"
      onClick={() => setTheme(NEXT[theme])}
      aria-label={`Theme: ${LABEL[theme]}. Click to switch.`}
      title={`Theme: ${LABEL[theme]}`}
    >
      <Icon />
    </Button>
  )
}
