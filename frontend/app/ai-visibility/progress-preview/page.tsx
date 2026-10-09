import { notFound } from 'next/navigation'
import ProgressPreview from './ProgressPreview'

export default function Page() {
  if (process.env.NODE_ENV !== 'development') notFound()
  return <ProgressPreview />
}
