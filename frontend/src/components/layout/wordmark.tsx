export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 ring-1 ring-primary/30">
        <span className="font-devanagari text-primary text-lg leading-none">व्या</span>
      </div>
      <span className="text-[15px] font-semibold tracking-tight">
        Vyakhya
        <span className="font-devanagari ml-1.5 text-muted-foreground font-normal">व्याख्या</span>
      </span>
    </div>
  );
}