export type BacklinkTab =
  | 'overview'
  | 'backlinks'
  | 'domains'
  | 'events'
  | 'opportunities'

const TAB_LABELS: Record<BacklinkTab, string> = {
  overview: 'Overview',
  backlinks: 'Backlinks',
  domains: 'Referring domains',
  events: 'New & lost',
  opportunities: 'Opportunities',
}

export default function BacklinkTabs({
  activeTab,
  onChange,
}: {
  activeTab: BacklinkTab
  onChange: (tab: BacklinkTab) => void
}) {
  const tabs = Object.keys(TAB_LABELS) as BacklinkTab[]

  return (
    <nav
      aria-label="Backlink profile sections"
      className="mt-4 overflow-x-auto border-b border-surface-border"
    >
      <div role="tablist" className="flex min-w-max gap-1">
        {tabs.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            id={`backlinks-tab-${tab}`}
            aria-controls={`backlinks-panel-${tab}`}
            aria-selected={activeTab === tab}
            tabIndex={activeTab === tab ? 0 : -1}
            onClick={() => onChange(tab)}
            onKeyDown={(event) => {
              const currentIndex = tabs.indexOf(tab)
              const nextIndex =
                event.key === 'ArrowRight'
                  ? (currentIndex + 1) % tabs.length
                  : event.key === 'ArrowLeft'
                    ? (currentIndex - 1 + tabs.length) % tabs.length
                    : event.key === 'Home'
                      ? 0
                      : event.key === 'End'
                        ? tabs.length - 1
                        : null
              if (nextIndex == null) return
              event.preventDefault()
              const nextTab = tabs[nextIndex]
              onChange(nextTab)
              document.getElementById(`backlinks-tab-${nextTab}`)?.focus()
            }}
            className={`min-h-[44px] border-b-2 px-4 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
              activeTab === tab
                ? 'border-primary text-primary-strong'
                : 'border-transparent text-surface-subtle hover:text-surface-foreground'
            }`}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>
    </nav>
  )
}
