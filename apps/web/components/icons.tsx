/**
 * The app's icon set: Hugeicons Free (Stroke Rounded, MIT), https://hugeicons.com.
 *
 * Every icon is a component with the name the app uses for it (Plus, Trash2, ChevronDown…), so
 * call sites read like before and size with classes (`size-4`) or the shadcn `[&_svg]` rules.
 * Icons are decorative by default (`aria-hidden`); pass `aria-label` to make one meaningful.
 * To change an icon, change its mapping here; nothing else imports the icon packages.
 */
import {
  Activity01Icon,
  Add01Icon,
  Alert02Icon,
  AlertCircleIcon,
  Archive02Icon,
  ArchiveArrowUpIcon,
  ArrowDown01Icon,
  ArrowDown02Icon,
  ArrowLeft01Icon,
  ArrowLeft02Icon,
  ArrowRight01Icon,
  ArrowRight02Icon,
  ArrowTurnBackwardIcon,
  ArrowUp01Icon,
  ArrowUp02Icon,
  BookmarkAdd02Icon,
  BubbleChatIcon,
  Calendar03Icon,
  CalendarAdd01Icon,
  CalendarCheckIn01Icon,
  CalendarRemove01Icon,
  Cancel01Icon,
  CancelCircleIcon,
  CheckListIcon,
  CheckmarkCircle02Icon,
  CheckmarkSquare02Icon,
  CircleIcon,
  Clock01Icon,
  CloudOffIcon,
  CodeIcon,
  Copy01Icon,
  DashboardSquare01Icon,
  DashedLineCircleIcon,
  Delete02Icon,
  Eraser01Icon,
  Exchange01Icon,
  File02Icon,
  FilterHorizontalIcon,
  FlashIcon,
  FloppyDiskIcon,
  Folder01Icon,
  GitBranchIcon,
  HandIcon,
  Heading01Icon,
  Heading02Icon,
  Heading03Icon,
  HelpCircleIcon,
  ImageAdd02Icon,
  Home01Icon,
  InboxIcon,
  InformationCircleIcon,
  Key01Icon,
  LaptopIcon,
  LeftToRightBlockQuoteIcon,
  LeftToRightListBulletIcon,
  LeftToRightListNumberIcon,
  LifebuoyIcon,
  Link01Icon,
  LinkSquare02Icon,
  Loading03Icon,
  Logout03Icon,
  Mail01Icon,
  MailRemove01Icon,
  MagicWand01Icon,
  Menu01Icon,
  Mic01Icon,
  Moon02Icon,
  MoreHorizontalIcon,
  NoteEditIcon,
  Notification02Icon,
  Notification03Icon,
  NotificationOff03Icon,
  PaintBoardIcon,
  ParagraphIcon,
  PauseCircleIcon,
  PencilEdit01Icon,
  PencilEdit02Icon,
  PlayIcon,
  Plug01Icon,
  PowerIcon,
  QuoteDownIcon,
  Redo02Icon,
  Refresh01Icon,
  RotateLeft01Icon,
  Search01Icon,
  SecurityBlockIcon,
  SecurityCheckIcon,
  SecurityIcon,
  SecurityWarningIcon,
  SentIcon,
  Settings01Icon,
  Settings05Icon,
  SidebarLeft01Icon,
  SidebarLeftIcon,
  SmartPhone01Icon,
  SparklesIcon,
  SquareIcon,
  SquareLock02Icon,
  StarIcon,
  StethoscopeIcon,
  Sun03Icon,
  Tag01Icon,
  TestTube01Icon,
  TextBoldIcon,
  TextItalicIcon,
  TextStrikethroughIcon,
  Tick02Icon,
  TickDouble02Icon,
  UnavailableIcon,
  Undo02Icon,
  UnfoldMoreIcon,
  Unlink04Icon,
  UserAdd01Icon,
  UserCircleIcon,
  UserGroupIcon,
  ViewIcon,
  ViewOffSlashIcon,
  VolumeHighIcon,
  VolumeLowIcon,
  VolumeOffIcon,
  WifiDisconnected02Icon,
  WorkflowSquare03Icon,
  WorkHistoryIcon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon, type HugeiconsProps, type IconSvgElement } from "@hugeicons/react";
import * as React from "react";

export type IconProps = Omit<HugeiconsProps, "icon" | "ref">;
/** Any icon from this module; use for props and lookup tables that hold an icon. */
export type IconComponent = React.ForwardRefExoticComponent<IconProps & React.RefAttributes<SVGSVGElement>>;

/** 1.75 keeps the rounded strokes crisp at the 14–16px sizes the UI mostly uses. */
const STROKE = 1.75;

function icon(svg: IconSvgElement, name: string): IconComponent {
  const Icon = React.forwardRef<SVGSVGElement, IconProps>(function Icon(props, ref) {
    const labelled = props["aria-label"] !== undefined || props["aria-labelledby"] !== undefined;
    return <HugeiconsIcon ref={ref} icon={svg} strokeWidth={STROKE} aria-hidden={labelled ? undefined : true} focusable="false" {...props} />;
  });
  Icon.displayName = name;
  return Icon;
}

// Navigation & layout
export const Home = icon(Home01Icon, "Home");
export const LayoutGrid = icon(DashboardSquare01Icon, "LayoutGrid");
export const Menu = icon(Menu01Icon, "Menu");
export const MoreHorizontal = icon(MoreHorizontalIcon, "MoreHorizontal");
export const PanelLeftClose = icon(SidebarLeft01Icon, "PanelLeftClose");
export const PanelLeftOpen = icon(SidebarLeftIcon, "PanelLeftOpen");
export const Settings = icon(Settings01Icon, "Settings");
export const Settings2 = icon(Settings05Icon, "Settings2");
export const ExternalLink = icon(LinkSquare02Icon, "ExternalLink");
export const LogOut = icon(Logout03Icon, "LogOut");

// Arrows & chevrons
export const ArrowDown = icon(ArrowDown02Icon, "ArrowDown");
export const ArrowLeft = icon(ArrowLeft02Icon, "ArrowLeft");
export const ArrowRight = icon(ArrowRight02Icon, "ArrowRight");
export const ArrowUp = icon(ArrowUp02Icon, "ArrowUp");
export const ChevronDown = icon(ArrowDown01Icon, "ChevronDown");
export const ChevronDownIcon = ChevronDown;
export const ChevronLeftIcon = icon(ArrowLeft01Icon, "ChevronLeft");
export const ChevronRight = icon(ArrowRight01Icon, "ChevronRight");
export const ChevronRightIcon = ChevronRight;
export const ChevronUp = icon(ArrowUp01Icon, "ChevronUp");
export const ChevronUpIcon = ChevronUp;
export const ChevronsUpDown = icon(UnfoldMoreIcon, "ChevronsUpDown");
export const CornerDownLeft = icon(ArrowTurnBackwardIcon, "CornerDownLeft");

// Actions
export const Plus = icon(Add01Icon, "Plus");
export const X = icon(Cancel01Icon, "X");
export const XIcon = X;
export const Check = icon(Tick02Icon, "Check");
export const CheckIcon = Check;
export const CheckCheck = icon(TickDouble02Icon, "CheckCheck");
export const Copy = icon(Copy01Icon, "Copy");
export const Trash2 = icon(Delete02Icon, "Trash2");
export const Pencil = icon(PencilEdit01Icon, "Pencil");
export const PenLine = icon(PencilEdit01Icon, "PenLine");
export const SquarePen = icon(PencilEdit02Icon, "SquarePen");
export const Save = icon(FloppyDiskIcon, "Save");
export const Search = icon(Search01Icon, "Search");
export const SearchIcon = Search;
export const Filter = icon(FilterHorizontalIcon, "Filter");
export const Send = icon(SentIcon, "Send");
export const RefreshCw = icon(Refresh01Icon, "RefreshCw");
export const RotateCcw = icon(RotateLeft01Icon, "RotateCcw");
export const Undo2 = icon(Undo02Icon, "Undo2");
export const Redo2 = icon(Redo02Icon, "Redo2");
export const Replace = icon(Exchange01Icon, "Replace");
export const Eraser = icon(Eraser01Icon, "Eraser");
export const Eye = icon(ViewIcon, "Eye");
export const EyeOff = icon(ViewOffSlashIcon, "EyeOff");
export const Play = icon(PlayIcon, "Play");
export const PauseCircle = icon(PauseCircleIcon, "PauseCircle");
export const Square = icon(SquareIcon, "Square");
export const Power = icon(PowerIcon, "Power");
export const Archive = icon(Archive02Icon, "Archive");
export const ArchiveRestore = icon(ArchiveArrowUpIcon, "ArchiveRestore");
export const BookmarkPlus = icon(BookmarkAdd02Icon, "BookmarkPlus");
export const Link = icon(Link01Icon, "Link");

// Status & feedback
export const AlertCircle = icon(AlertCircleIcon, "AlertCircle");
export const AlertTriangle = icon(Alert02Icon, "AlertTriangle");
export const TriangleAlertIcon = AlertTriangle;
export const InfoIcon = icon(InformationCircleIcon, "Info");
export const HelpCircle = icon(HelpCircleIcon, "HelpCircle");
export const CheckCircle2 = icon(CheckmarkCircle02Icon, "CheckCircle2");
export const CircleCheckIcon = CheckCircle2;
export const XCircle = icon(CancelCircleIcon, "XCircle");
export const OctagonXIcon = XCircle;
export const Circle = icon(CircleIcon, "Circle");
export const CircleDashed = icon(DashedLineCircleIcon, "CircleDashed");
export const CircleSlash = icon(UnavailableIcon, "CircleSlash");
export const Loader2 = icon(Loading03Icon, "Loader2");
export const Loader2Icon = Loader2;
export const Activity = icon(Activity01Icon, "Activity");
export const Zap = icon(FlashIcon, "Zap");
export const CloudOff = icon(CloudOffIcon, "CloudOff");
export const WifiOff = icon(WifiDisconnected02Icon, "WifiOff");
export const Star = icon(StarIcon, "Star");

// Notifications, sound & voice
export const Bell = icon(Notification03Icon, "Bell");
export const BellOff = icon(NotificationOff03Icon, "BellOff");
export const BellRing = icon(Notification02Icon, "BellRing");
export const Volume1 = icon(VolumeLowIcon, "Volume1");
export const Volume2 = icon(VolumeHighIcon, "Volume2");
export const VolumeX = icon(VolumeOffIcon, "VolumeX");
export const Mic = icon(Mic01Icon, "Mic");

// Content: notes, tasks, calendar, mail
export const NotebookPen = icon(NoteEditIcon, "NotebookPen");
export const FileText = icon(File02Icon, "FileText");
export const Folder = icon(Folder01Icon, "Folder");
export const Tag = icon(Tag01Icon, "Tag");
export const Inbox = icon(InboxIcon, "Inbox");
export const CheckSquare = icon(CheckmarkSquare02Icon, "CheckSquare");
export const ListChecks = icon(CheckListIcon, "ListChecks");
export const CalendarIcon = icon(Calendar03Icon, "Calendar");
export const CalendarDays = CalendarIcon;
export const CalendarCheck = icon(CalendarCheckIn01Icon, "CalendarCheck");
export const CalendarPlus = icon(CalendarAdd01Icon, "CalendarPlus");
export const CalendarX = icon(CalendarRemove01Icon, "CalendarX");
export const Clock = icon(Clock01Icon, "Clock");
export const History = icon(WorkHistoryIcon, "History");
export const Mail = icon(Mail01Icon, "Mail");
export const MailX = icon(MailRemove01Icon, "MailX");
export const MessageSquareText = icon(BubbleChatIcon, "MessageSquareText");

// Editor formatting
export const Bold = icon(TextBoldIcon, "Bold");
export const Italic = icon(TextItalicIcon, "Italic");
export const Strikethrough = icon(TextStrikethroughIcon, "Strikethrough");
export const Heading1 = icon(Heading01Icon, "Heading1");
export const Heading2 = icon(Heading02Icon, "Heading2");
export const Heading3 = icon(Heading03Icon, "Heading3");
export const Pilcrow = icon(ParagraphIcon, "Pilcrow");
export const List = icon(LeftToRightListBulletIcon, "List");
export const ListOrdered = icon(LeftToRightListNumberIcon, "ListOrdered");
export const Quote = icon(QuoteDownIcon, "Quote");
export const TextQuote = icon(LeftToRightBlockQuoteIcon, "TextQuote");
export const Braces = icon(CodeIcon, "Braces");

// AI & automation
export const Sparkles = icon(SparklesIcon, "Sparkles");
export const WandSparkles = icon(MagicWand01Icon, "WandSparkles");
export const Workflow = icon(WorkflowSquare03Icon, "Workflow");
export const GitBranch = icon(GitBranchIcon, "GitBranch");
export const Hand = icon(HandIcon, "Hand");
export const FlaskConical = icon(TestTube01Icon, "FlaskConical");
export const Stethoscope = icon(StethoscopeIcon, "Stethoscope");
export const Plug = icon(Plug01Icon, "Plug");
export const Unplug = icon(Unlink04Icon, "Unplug");

// Account, security & devices
export const UserRound = icon(UserCircleIcon, "UserRound");
export const UserPlus = icon(UserAdd01Icon, "UserPlus");
export const Users = icon(UserGroupIcon, "Users");
export const KeyRound = icon(Key01Icon, "KeyRound");
export const Lock = icon(SquareLock02Icon, "Lock");
export const ShieldCheck = icon(SecurityCheckIcon, "ShieldCheck");
export const ShieldAlert = icon(SecurityWarningIcon, "ShieldAlert");
export const ShieldQuestion = icon(SecurityIcon, "ShieldQuestion");
export const ShieldX = icon(SecurityBlockIcon, "ShieldX");
export const Laptop = icon(LaptopIcon, "Laptop");
export const Smartphone = icon(SmartPhone01Icon, "Smartphone");
export const LifeBuoy = icon(LifebuoyIcon, "LifeBuoy");

// Appearance
export const Sun = icon(Sun03Icon, "Sun");
export const Moon = icon(Moon02Icon, "Moon");
export const Palette = icon(PaintBoardIcon, "Palette");
export const ImagePlus = icon(ImageAdd02Icon, "ImagePlus");
