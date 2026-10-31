import * as React from "react"
import { cn } from "cn"

function Progress({ className, value, max = 100, ...props }: React.ComponentProps<"progress">) {
  return <progress data-slot="progress" className={cn("progress-native", className)} value={value} max={max} {...props} />
}

export { Progress }
