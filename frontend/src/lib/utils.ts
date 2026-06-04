import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function createId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}
