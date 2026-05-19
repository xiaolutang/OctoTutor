import Link from "next/link"

export function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto flex h-14 items-center px-4">
        <Link href="/" className="flex items-center space-x-2">
          <span className="text-xl font-bold">🐙</span>
          <span className="text-lg font-semibold">章鱼哥解题 OctoTutor</span>
        </Link>
        <nav className="ml-8 flex items-center space-x-6 text-sm font-medium">
          <Link
            href="/chat"
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            解题对话
          </Link>
        </nav>
      </div>
    </header>
  )
}
