import React, { createContext, useContext, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Check, Loader2, Circle, ChevronDown } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ShimmerText } from "@/components/ui/components-ai-thought-chain-utils/text-shimmer";

export type Status = "done" | "active" | "pending";

type StepContextType = {
  open: boolean;
  setOpen: React.Dispatch<React.SetStateAction<boolean>>;
  status: Status;
};

const StepContext = createContext<StepContextType | null>(null);

const statusStyles: Record<
  Status,
  { label: string; line: string; badge: string }
> = {
  done: {
    label: "text-muted-foreground",
    line: "bg-emerald-600/30 dark:bg-emerald-500/30",
    badge: "",
  },
  active: {
    label: "text-foreground font-semibold",
    line: "bg-blue-500/25 dark:bg-blue-400/25",
    badge: "bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-400",
  },
  pending: {
    label: "text-muted-foreground/60",
    line: "bg-border",
    badge: "",
  },
};

function StatusIcon({ status }: { status: Status }) {
  if (status === "done") {
    return (
      <span className="flex size-5 items-center justify-center rounded-full bg-emerald-600 shadow-sm">
        <Check className="size-3 text-white" strokeWidth={3} />
      </span>
    );
  }

  if (status === "active") {
    return (
      <motion.span
        animate={{ rotate: 360 }}
        transition={{ repeat: Infinity, duration: 0.75, ease: "linear" }}
        className="flex size-5 items-center justify-center text-blue-600 dark:text-blue-400"
      >
        <Loader2 className="size-5" />
      </motion.span>
    );
  }

  return <Circle className="size-5 text-muted-foreground/40" />;
}

export function ThoughtChain({ children }: { children: React.ReactNode }) {
  const steps = React.Children.toArray(children);
  const total = steps.length;

  return (
    <div className="space-y-1.5 select-none my-1">
      {steps.map((step, index) =>
        React.isValidElement(step)
          ? React.cloneElement(
              step as React.ReactElement<{ _isLast?: boolean }>,
              {
                _isLast: index === total - 1,
              },
            )
          : step,
      )}
    </div>
  );
}

export function ThoughtChainStep({
  children,
  status = "pending",
  defaultOpen = true,
  _isLast = false,
}: {
  children: React.ReactNode;
  status?: Status;
  defaultOpen?: boolean;
  _isLast?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const styles = statusStyles[status];

  return (
    <StepContext.Provider value={{ open, setOpen, status }}>
      <Collapsible open={open} onOpenChange={setOpen}>
        <div className="flex gap-3.5">
          <div className="flex shrink-0 flex-col items-center">
            <span className="mt-0.5">
              <StatusIcon status={status} />
            </span>

            {!_isLast && (
              <span
                className={cn(
                  "mt-1.5 min-h-5 w-0.5 flex-1 rounded-sm",
                  styles.line,
                )}
              />
            )}
          </div>

          <div className="flex-1 pb-2">{children}</div>
        </div>
      </Collapsible>
    </StepContext.Provider>
  );
}

export function ThoughtChainTrigger({
  children,
  latencyMs,
}: {
  children: React.ReactNode;
  latencyMs?: number | string;
}) {
  const { open, status } = useContext(StepContext)!;
  const styles = statusStyles[status];

  return (
    <CollapsibleTrigger className="flex cursor-pointer select-none items-center gap-1.5 outline-none text-left w-full group">
      <span
        className={cn(
          "text-[13.5px] font-semibold tracking-tight transition-colors",
          styles.label,
        )}
      >
        {status === "active" ? (
          typeof children === "string" ? (
            <ShimmerText text={children} />
          ) : (
            children
          )
        ) : (
          children
        )}
      </span>

      <motion.span
        animate={{ rotate: open ? 180 : 0 }}
        transition={{ duration: 0.2, ease: "easeInOut" }}
        className="flex items-center text-muted-foreground ml-1"
      >
        <ChevronDown className="size-3.5" />
      </motion.span>

      {status === "active" && (
        <Badge
          variant="outline"
          className={cn(styles.badge, "border-blue-200 dark:border-blue-800 ml-auto text-[10.5px]")}
        >
          In progress
        </Badge>
      )}

      {status === "done" && latencyMs !== undefined && (
        <span className="ml-auto font-mono text-[10.5px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded border border-border">
          {latencyMs}ms
        </span>
      )}
    </CollapsibleTrigger>
  );
}

export function ThoughtChainContent({
  children,
}: {
  children: React.ReactNode;
}) {
  const { open } = useContext(StepContext)!;

  return (
    <CollapsibleContent forceMount>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="content"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.22, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="mt-1 pl-0.5 space-y-0.5">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </CollapsibleContent>
  );
}

export function ThoughtChainItem({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="flex items-start gap-2 py-1"
    >
      <span className="mt-1.5 size-1 shrink-0 rounded-full bg-muted-foreground/60" />
      <span className="text-[12.5px] leading-relaxed text-muted-foreground">
        {children}
      </span>
    </motion.div>
  );
}

export default ThoughtChain;
