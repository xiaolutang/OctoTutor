"use client"

import { useEffect, useRef, useCallback } from "react"

/**
 * 庆祝动效 Overlay
 *
 * Canvas 2D 粒子火焰系统 + 章鱼哥主题庆祝文案。
 * 仅在开发环境使用，不进入生产构建。
 */

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  life: number
  maxLife: number
  size: number
  layer: number
}

const PARTICLE_COUNT = 300
const LAYERS = 3

const FIRE_COLORS = [
  // 外层 → 内层
  ["#ff1a1a", "#ff4d00", "#ff9900", "#ffcc00"],
  ["#ff3300", "#ff6600", "#ffaa00", "#ffdd33"],
  ["#cc0000", "#ff2200", "#ff7700", "#ffbb22"],
]

function createParticle(canvas: HTMLCanvasElement, layer: number): Particle {
  const w = canvas.width
  const h = canvas.height
  const spread = w * 0.6
  const centerX = w / 2

  return {
    x: centerX + (Math.random() - 0.5) * spread,
    y: h + Math.random() * 20,
    vx: (Math.random() - 0.5) * 1.5,
    vy: -(2 + Math.random() * 4) * (1 + layer * 0.3),
    life: 0,
    maxLife: 60 + Math.random() * 80,
    size: 3 + Math.random() * 6 - layer * 1.5,
    layer,
  }
}

function updateParticle(p: Particle): boolean {
  p.life++
  p.x += p.vx + (Math.random() - 0.5) * 0.8
  p.y += p.vy
  p.vy *= 0.99
  p.size *= 0.995
  return p.life < p.maxLife && p.size > 0.3
}

function drawParticle(ctx: CanvasRenderingContext2D, p: Particle) {
  const progress = p.life / p.maxLife
  const colors = FIRE_COLORS[p.layer % FIRE_COLORS.length]
  const colorIndex = Math.min(Math.floor(progress * colors.length), colors.length - 1)
  const color = colors[colorIndex]
  const alpha = Math.max(0, 1 - progress * 1.2)

  ctx.beginPath()
  ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
  ctx.fillStyle = color
  ctx.globalAlpha = alpha * 0.8
  ctx.fill()

  // 发光效果
  if (progress < 0.4) {
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.size * 2, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.globalAlpha = alpha * 0.15
    ctx.fill()
  }
}

export function CelebrationOverlay({ onClose }: { onClose: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const particlesRef = useRef<Particle[]>([])
  const frameRef = useRef<number>(0)

  // ESC 键监听
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [onClose])

  // Canvas 动画循环
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    function resize() {
      if (!canvas) return
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }
    resize()
    window.addEventListener("resize", resize)

    // 初始化粒子
    particlesRef.current = []
    for (let layer = 0; layer < LAYERS; layer++) {
      for (let i = 0; i < PARTICLE_COUNT / LAYERS; i++) {
        particlesRef.current.push(createParticle(canvas, layer))
      }
    }

    function animate() {
      if (!canvas || !ctx) return
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      // 半透明黑色背景
      ctx.fillStyle = "rgba(0, 0, 0, 0.15)"
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      // 更新和绘制粒子
      particlesRef.current = particlesRef.current.filter((p) => {
        const alive = updateParticle(p)
        if (alive) {
          drawParticle(ctx, p)
        }
        return alive
      })

      // 补充新粒子
      const targetCount = PARTICLE_COUNT
      const deficit = targetCount - particlesRef.current.length
      for (let i = 0; i < deficit; i++) {
        const layer = i % LAYERS
        particlesRef.current.push(createParticle(canvas, layer))
      }

      ctx.globalAlpha = 1
      frameRef.current = requestAnimationFrame(animate)
    }

    frameRef.current = requestAnimationFrame(animate)

    return () => {
      window.removeEventListener("resize", resize)
      cancelAnimationFrame(frameRef.current)
    }
  }, [])

  const handleClose = useCallback(() => {
    cancelAnimationFrame(frameRef.current)
    onClose()
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <canvas ref={canvasRef} className="absolute inset-0" />

      {/* 庆祝文案 */}
      <div className="relative z-10 text-center pointer-events-none select-none">
        <div className="text-6xl mb-6 animate-bounce">🐙</div>
        <h2
          className="text-4xl sm:text-5xl font-black text-transparent bg-clip-text pb-2"
          style={{
            backgroundImage:
              "linear-gradient(to right, #ff6600, #ffcc00, #ff9900, #ffdd33)",
          }}
        >
          章鱼哥解题
        </h2>
        <p className="mt-3 text-xl sm:text-2xl font-bold text-orange-300">
          基础架构搭建完成
        </p>
        <p className="mt-2 text-base text-yellow-200/80">
          八臂齐开，难题自然解开
        </p>
        <div className="mt-6 flex items-center justify-center gap-3 text-sm text-orange-200/60">
          <span>Next.js 16</span>
          <span>·</span>
          <span>OAuth 2.0 + PKCE</span>
          <span>·</span>
          <span>Docker Standalone</span>
        </div>
        <div className="mt-2 text-sm text-orange-200/60">
          R001 归档 · 6/6 任务完成 · 全部测试通过
        </div>
      </div>

      {/* 关闭按钮 */}
      <button
        onClick={handleClose}
        className="absolute top-6 right-6 z-20 px-4 py-2 rounded-lg bg-black/40 text-white/80 text-sm hover:bg-black/60 transition-colors backdrop-blur-sm border border-white/10"
      >
        关闭 (ESC)
      </button>
    </div>
  )
}
