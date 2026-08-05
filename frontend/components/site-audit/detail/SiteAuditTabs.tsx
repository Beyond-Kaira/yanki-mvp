export type SiteAuditTab = 'overview' | 'issues' | 'pages' | 'schema'

const TAB_LABELS: Record<SiteAuditTab, string> = {
  overview: 'Overview',
  issues: 'Issues',
  pages: 'Crawled pages',
  schema: 'Schema markup',
}

export default function SiteAuditTabs({
  activeTab,
  onChange,
}: {
  activeTab: SiteAuditTab
  onChange: (tab: SiteAuditTab) => void
}) {
  const tabs = Object.keys(TAB_LABELS) as SiteAuditTab[]

  return (
    <nav
      aria-label="Site Audit result sections"
      className="mt-5 overflow-x-auto border-b border-surface-border"
    >
      <div role="tablist" className="flex min-w-max gap-1">
        {tabs.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            id={`site-audit-tab-${tab}`}
            aria-controls={`site-audit-panel-${tab}`}
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
              document.getElementById(`site-audit-tab-${nextTab}`)?.focus()
            }}
            className={`min-h-[44px] border-b-2 px-4 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
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
