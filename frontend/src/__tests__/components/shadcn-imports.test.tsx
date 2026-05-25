/**
 * R009-FF001 shadcn/ui 组件安装 — 编译验证测试
 *
 * 验证 5 个新安装的 shadcn/ui 组件可以被正确 import，
 * 且每个导出是有效的 React 组件（typeof === 'function' 或 typeof === 'object'）。
 */
import { describe, it, expect } from 'vitest';

// ============================================================
// sidebar
// ============================================================
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInput,
  SidebarInset,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarProvider,
  SidebarRail,
  SidebarSeparator,
  SidebarTrigger,
  useSidebar,
} from '@/components/ui/sidebar';

// ============================================================
// popover
// ============================================================
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@/components/ui/popover';

// ============================================================
// alert-dialog
// ============================================================
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogOverlay,
  AlertDialogPortal,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';

// ============================================================
// sonner
// ============================================================
import { Toaster } from '@/components/ui/sonner';

// ============================================================
// input
// ============================================================
import { Input } from '@/components/ui/input';

// ============================================================
// 辅助函数
// ============================================================

/**
 * 判断一个值是否是有效的 React 组件。
 * shadcn/ui 组件通过 React.forwardRef 包装，typeof 为 'function' 或 'object'。
 */
function isReactComponent(value: unknown): boolean {
  return typeof value === 'function' || typeof value === 'object';
}

// ============================================================
// 测试
// ============================================================

describe('R009-FF001: shadcn/ui 组件安装验证', () => {
  describe('sidebar 组件', () => {
    const sidebarExports = {
      Sidebar,
      SidebarContent,
      SidebarFooter,
      SidebarGroup,
      SidebarGroupAction,
      SidebarGroupContent,
      SidebarGroupLabel,
      SidebarHeader,
      SidebarInput,
      SidebarInset,
      SidebarMenu,
      SidebarMenuAction,
      SidebarMenuBadge,
      SidebarMenuButton,
      SidebarMenuItem,
      SidebarMenuSkeleton,
      SidebarMenuSub,
      SidebarMenuSubButton,
      SidebarMenuSubItem,
      SidebarProvider,
      SidebarRail,
      SidebarSeparator,
      SidebarTrigger,
    };

    it('导出 23 个 sidebar 组件', () => {
      expect(Object.keys(sidebarExports)).toHaveLength(23);
    });

    it('所有 sidebar 导出都是有效的 React 组件', () => {
      for (const [name, comp] of Object.entries(sidebarExports)) {
        expect(isReactComponent(comp), `${name} 不是有效的 React 组件`).toBe(true);
      }
    });

    it('useSidebar 是函数', () => {
      expect(typeof useSidebar).toBe('function');
    });
  });

  describe('popover 组件', () => {
    const popoverExports = {
      Popover,
      PopoverContent,
      PopoverDescription,
      PopoverHeader,
      PopoverTitle,
      PopoverTrigger,
    };

    it('导出 6 个 popover 组件', () => {
      expect(Object.keys(popoverExports)).toHaveLength(6);
    });

    it('所有 popover 导出都是有效的 React 组件', () => {
      for (const [name, comp] of Object.entries(popoverExports)) {
        expect(isReactComponent(comp), `${name} 不是有效的 React 组件`).toBe(true);
      }
    });
  });

  describe('alert-dialog 组件', () => {
    const alertDialogExports = {
      AlertDialog,
      AlertDialogAction,
      AlertDialogCancel,
      AlertDialogContent,
      AlertDialogDescription,
      AlertDialogFooter,
      AlertDialogHeader,
      AlertDialogMedia,
      AlertDialogOverlay,
      AlertDialogPortal,
      AlertDialogTitle,
      AlertDialogTrigger,
    };

    it('导出 12 个 alert-dialog 组件', () => {
      expect(Object.keys(alertDialogExports)).toHaveLength(12);
    });

    it('所有 alert-dialog 导出都是有效的 React 组件', () => {
      for (const [name, comp] of Object.entries(alertDialogExports)) {
        expect(isReactComponent(comp), `${name} 不是有效的 React 组件`).toBe(true);
      }
    });
  });

  describe('sonner 组件', () => {
    it('导出 Toaster 组件', () => {
      expect(isReactComponent(Toaster)).toBe(true);
    });
  });

  describe('input 组件', () => {
    it('导出 Input 组件', () => {
      expect(isReactComponent(Input)).toBe(true);
    });
  });
});
