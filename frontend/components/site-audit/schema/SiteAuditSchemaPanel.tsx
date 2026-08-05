import type { SiteAuditPage, SiteAuditSchema } from '@/lib/contracts'
import EmptyPanel from '@/components/site-audit/shared/EmptyPanel'

type SchemaStatus = 'passed' | 'warning' | 'error'

function schemaStatus(schema: SiteAuditSchema): SchemaStatus {
  if (!schema.syntax_valid || (schema.details?.invalid_fields?.length ?? 0) > 0) {
    return 'error'
  }
  if (schema.structure_status.toLowerCase().startsWith('warning')) {
    return 'warning'
  }
  return 'passed'
}

const STATUS_LABEL: Record<SchemaStatus, string> = {
  passed: 'Checks passed',
  warning: 'Needs review',
  error: 'Validation issue',
}

const STATUS_TONE: Record<SchemaStatus, string> = {
  passed: 'bg-success-soft text-success-strong',
  warning: 'bg-warning-soft text-warning-strong',
  error: 'bg-danger-soft text-danger-strong',
}

export default function SiteAuditSchemaPanel({ pages }: { pages: SiteAuditPage[] }) {
  const schemaPages = pages
    .filter((page) => page.schemas.length > 0)
    .map((page) => ({
      page,
      schemas: page.schemas.map((schema) => ({
        schema,
        status: schemaStatus(schema),
      })),
    }))

  const allSchemas = schemaPages.flatMap((entry) => entry.schemas)
  const summary = {
    total: allSchemas.length,
    passed: allSchemas.filter((entry) => entry.status === 'passed').length,
    warnings: allSchemas.filter((entry) => entry.status === 'warning').length,
    errors: allSchemas.filter((entry) => entry.status === 'error').length,
  }

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-surface-border bg-surface p-6 shadow-sm">
        <p className="font-mono text-xs font-medium uppercase tracking-[0.16em] text-primary-strong">
          Structured data
        </p>
        <h2 className="mt-2 text-2xl font-semibold text-surface-foreground">
          Schema markup
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-surface-subtle">
          Validation is limited to JSON syntax, recognized Schema.org types, and
          the field checks returned by the backend. “Checks passed” is not a claim
          of complete Schema.org validity.
        </p>

        <dl className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <SummaryCard label="Detected" value={summary.total} />
          <SummaryCard label="Checks passed" value={summary.passed} tone="success" />
          <SummaryCard label="Needs review" value={summary.warnings} tone="warning" />
          <SummaryCard label="Validation issues" value={summary.errors} tone="danger" />
          <SummaryCard label="Pages with schema" value={schemaPages.length} />
        </dl>
      </section>

      {!schemaPages.length ? (
        <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
          <EmptyPanel
            title="No schema markup found"
            message="None of the crawled pages contained detectable JSON-LD schema markup."
          />
        </section>
      ) : (
        <div className="space-y-4">
          {schemaPages.map(({ page, schemas }) => (
            <article
              key={page.id}
              className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm"
            >
              <header className="flex flex-col gap-2 border-b border-surface-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
                <div className="min-w-0">
                  <h3 className="truncate font-semibold text-surface-foreground">
                    {page.title || 'Untitled page'}
                  </h3>
                  <a
                    href={page.final_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 block truncate text-xs text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    {page.final_url}
                  </a>
                </div>
                <span className="text-sm text-surface-subtle">
                  {schemas.length} {schemas.length === 1 ? 'schema' : 'schemas'}
                </span>
              </header>

              <ul className="divide-y divide-surface-border">
                {schemas.map(({ schema, status }, index) => (
                  <li key={`${schema.type}-${index}`} className="px-5 py-5 sm:px-6">
                    <div className="flex flex-wrap items-center gap-3">
                      <p className="font-semibold text-surface-foreground">
                        {schema.type}
                      </p>
                      <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_TONE[status]}`}>
                        {STATUS_LABEL[status]}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-surface-subtle">
                      {schema.structure_status}
                    </p>
                    {schema.error_detail ? (
                      <p className="mt-3 rounded-lg bg-danger-soft p-3 text-sm text-danger-strong">
                        {schema.error_detail}
                      </p>
                    ) : null}
                    <SchemaFields schema={schema} />
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

function SummaryCard({
  label,
  value,
  tone = 'default',
}: {
  label: string
  value: number
  tone?: 'default' | 'success' | 'warning' | 'danger'
}) {
  const toneClass = {
    default: 'text-surface-foreground',
    success: 'text-success-strong',
    warning: 'text-warning-strong',
    danger: 'text-danger-strong',
  }[tone]
  return (
    <div className="rounded-lg bg-surface-muted p-4">
      <dt className="text-xs text-surface-subtle">{label}</dt>
      <dd className={`mt-2 text-2xl font-semibold ${toneClass}`}>{value}</dd>
    </div>
  )
}

function SchemaFields({ schema }: { schema: SiteAuditSchema }) {
  const validFields = schema.details?.valid_fields ?? []
  const invalidFields = schema.details?.invalid_fields ?? []
  if (!validFields.length && !invalidFields.length) return null

  return (
    <div className="mt-4 grid gap-4 sm:grid-cols-2">
      <FieldList label="Accepted fields" fields={validFields} tone="success" />
      <FieldList label="Fields needing review" fields={invalidFields} tone="danger" />
    </div>
  )
}

function FieldList({
  label,
  fields,
  tone,
}: {
  label: string
  fields: string[]
  tone: 'success' | 'danger'
}) {
  return (
    <div>
      <p className="text-xs font-medium text-surface-subtle">{label}</p>
      {fields.length ? (
        <ul className="mt-2 flex flex-wrap gap-2">
          {fields.map((field) => (
            <li
              key={field}
              className={`rounded-full px-2.5 py-1 font-mono text-xs ${
                tone === 'success'
                  ? 'bg-success-soft text-success-strong'
                  : 'bg-danger-soft text-danger-strong'
              }`}
            >
              {field}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-surface-subtle">—</p>
      )}
    </div>
  )
}
