import Link from "next/link"

export default function Home() {
  return (
    <div className="container mx-auto px-4 py-16">
      <section className="mx-auto max-w-3xl text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          章鱼哥解题
        </h1>
        <p className="mt-2 text-lg text-muted-foreground">
          OctoTutor -- 八臂齐开，难题自然解开
        </p>
        <p className="mt-6 text-base leading-7 text-muted-foreground">
          基于高中数学的智能教学助手，帮助高中生更高效地学习数学。
          上传题目图片或输入题目描述，章鱼哥会为你提供详细的解题思路和步骤。
        </p>
        <div className="mt-8 flex items-center justify-center gap-4">
          <Link
            href="/chat"
            className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-8 text-sm font-medium text-primary-foreground ring-offset-background transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            开始解题
          </Link>
        </div>
      </section>

      <section className="mx-auto mt-20 max-w-4xl">
        <h2 className="text-center text-2xl font-bold tracking-tight">
          核心功能
        </h2>
        <div className="mt-8 grid gap-6 sm:grid-cols-3">
          <div className="rounded-lg border bg-card p-6 text-card-foreground">
            <h3 className="font-semibold">图片识别</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              拍照上传数学题目，自动识别题目内容
            </p>
          </div>
          <div className="rounded-lg border bg-card p-6 text-card-foreground">
            <h3 className="font-semibold">详细解答</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              提供完整的解题思路和步骤，不只是答案
            </p>
          </div>
          <div className="rounded-lg border bg-card p-6 text-card-foreground">
            <h3 className="font-semibold">公式渲染</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              数学公式完美渲染，清晰展示每一步
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}
