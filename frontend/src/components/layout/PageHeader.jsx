export function PageHeader({ title, description, action }) {
  return (
    <div className="mb-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between pb-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight font-display">{title}</h1>
          {description && (
            <p className="text-sm mt-1 text-muted-foreground">{description}</p>
          )}
        </div>
        {action && (
          <div className="w-full sm:w-auto sm:ml-4 shrink-0">{action}</div>
        )}
      </div>
      <div className="executive-divider" aria-hidden />
    </div>
  )
}
