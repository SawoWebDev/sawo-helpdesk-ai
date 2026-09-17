import {
  BarChart3,
  BookOpen,
  Grid2x2,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  MessageCircleQuestion,
  MessageSquareText,
  Settings,
  Users,
} from "lucide-react";

const SIZE = 18;
const STROKE = 2;

export function DashboardIcon() {
  return <LayoutDashboard size={SIZE} strokeWidth={STROKE} className="shrink-0" />;
}

export function AnalyticsIcon() {
  return <BarChart3 size={SIZE} strokeWidth={STROKE} className="shrink-0" />;
}

export function LibraryIcon() {
  return <BookOpen size={SIZE} strokeWidth={STROKE} className="shrink-0" />;
}

export function FaqIcon() {
  return <MessageCircleQuestion size={SIZE} strokeWidth={STROKE} className="shrink-0" />;
}

export function CategoriesIcon() {
  return <Grid2x2 size={SIZE} strokeWidth={STROKE} className="shrink-0" />;
}

export function UnansweredIcon() {
  return <HelpCircle size={SIZE} strokeWidth={STROKE} className="shrink-0" />;
}

export function LogsIcon() {
  return <MessageSquareText size={SIZE} strokeWidth={STROKE} className="shrink-0" />;
}

export function SettingsIcon() {
  return <Settings size={SIZE} strokeWidth={STROKE} className="shrink-0" />;
}

export function UsersIcon() {
  return <Users size={SIZE} strokeWidth={STROKE} className="shrink-0" />;
}

export function LogoutIcon() {
  return <LogOut size={SIZE} strokeWidth={STROKE} className="shrink-0" />;
}
