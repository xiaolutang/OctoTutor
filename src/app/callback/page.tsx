export default function CallbackPage() {
  return (
    <div className="container mx-auto flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-4">
      <div className="text-center">
        <h1 className="text-2xl font-bold">OAuth 回调</h1>
        <p className="mt-2 text-muted-foreground">
          正在处理登录回调...
        </p>
      </div>
    </div>
  )
}
