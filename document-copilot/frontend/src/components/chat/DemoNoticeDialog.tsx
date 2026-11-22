import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { env } from '@/lib/env'

interface Props {
  open: boolean
  onClose: () => void
}

// Shown when a visitor tries to ask something the assistant would have to answer live. Every
// live answer spends the owner's model tokens, so those are limited to approved accounts; the
// sample questions and the rest of the app stay open.
export default function DemoNoticeDialog({ open, onClose }: Props) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Live questions are by invitation</DialogTitle>
          <DialogDescription>
            Document Copilot answers from SEC filings using a language model, so live questions are
            limited to approved demo accounts while this project is a private demo.
          </DialogDescription>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          You can still look around and try the <strong className="text-foreground">sample questions</strong>{' '}
          on the home screen to see how an answer, its sources and the filing passages behind each
          figure work. To see a live demo, please reach out to{' '}
          <strong className="text-foreground">Akshay Ratnawat</strong>.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          {env.contactUrl && (
            <Button render={<a href={env.contactUrl} target="_blank" rel="noreferrer" />}>
              Contact Akshay
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
