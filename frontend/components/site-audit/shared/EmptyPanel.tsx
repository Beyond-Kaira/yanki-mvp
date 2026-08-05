export default function EmptyPanel({
  title,
  message,
}: {
  title?: string
  message: string
}) {
  return (
    <div className="p-6 sm:p-8">
      {title ? (
        <h3 className="font-semibold text-surface-foreground">{title}</h3>
      ) : null}
      <p className={`${title ? 'mt-1' : ''} text-sm text-surface-subtle`}>
        {message}
      </p>
    </div>
  )
}
