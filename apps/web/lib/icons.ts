import { createElement } from "react";
import {
  AddressBook,
  ArrowCounterClockwise,
  ArrowLeft,
  ArrowRight,
  ArrowSquareOut,
  ArrowUp,
  ArrowsClockwise,
  Books,
  Broadcast,
  Calculator,
  CalendarDots,
  CaretDown,
  CaretRight,
  CaretUp,
  CaretUpDown,
  ChatCircle,
  Check,
  CheckCircle,
  CircleDashed,
  CircleNotch,
  Columns,
  Compass,
  Copy,
  Eye,
  EyeSlash,
  DotsThree,
  DotsThreeVertical,
  DownloadSimple,
  FileText,
  FolderOpen,
  Gear,
  Image,
  Info,
  Link,
  MagnifyingGlass,
  MapPin,
  Microphone,
  Minus,
  MinusCircle,
  Monitor,
  Moon,
  Newspaper,
  PaperPlaneTilt,
  Paperclip,
  PencilSimple,
  Phone,
  Play,
  Plus,
  Printer,
  Question,
  Radio,
  Robot,
  Rows,
  Scan,
  SealCheck,
  ShareNetwork,
  ShieldCheck,
  SignOut,
  Sparkle,
  SpeakerHigh,
  Stamp,
  Stop,
  Sun,
  TextT,
  Timer,
  Users,
  VideoCamera,
  Warning,
  Waveform,
  WifiSlash,
  X,
  XCircle,
} from "@phosphor-icons/react/ssr";
import type { IconProps } from "@phosphor-icons/react";
type PhosphorIcon = React.ComponentType<IconProps>;

// One map for every icon on the desk and the public site: Phosphor, duotone weight.
// Size comes from the className (size-4...) because the svg is 1em by default.
export type Icon = React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;

function duo(Glyph: PhosphorIcon): Icon {
  const Wrapped: Icon = ({ className, "aria-hidden": hidden }) =>
    createElement(Glyph, { className, "aria-hidden": hidden, weight: "duotone", size: "1em" });
  return Wrapped;
}

export const IconArrowCounterClockwise = duo(ArrowCounterClockwise);
export const IconArrowLeft = duo(ArrowLeft);
export const IconArrowRight = duo(ArrowRight);
export const IconArrowsClockwise = duo(ArrowsClockwise);
export const IconArrowSquareOut = duo(ArrowSquareOut);
export const IconArrowUp = duo(ArrowUp);
export const IconBooks = duo(Books);
export const IconCalendarDots = duo(CalendarDots);
export const IconCaretDown = duo(CaretDown);
export const IconCaretRight = duo(CaretRight);
export const IconCaretUp = duo(CaretUp);
export const IconCaretUpDown = duo(CaretUpDown);
export const IconChatCircle = duo(ChatCircle);
export const IconCheck = duo(Check);
export const IconCheckCircle = duo(CheckCircle);
export const IconCircleDashed = duo(CircleDashed);
export const IconCircleNotch = duo(CircleNotch);
export const IconColumns = duo(Columns);
export const IconCopy = duo(Copy);
export const IconDotsThree = duo(DotsThree);
export const IconDotsThreeVertical = duo(DotsThreeVertical);
export const IconDownloadSimple = duo(DownloadSimple);
export const IconFileText = duo(FileText);
export const IconFolderOpen = duo(FolderOpen);
export const IconGear = duo(Gear);
export const IconImage = duo(Image);
export const IconInfo = duo(Info);
export const IconLink = duo(Link);
export const IconMagnifyingGlass = duo(MagnifyingGlass);
export const IconMapPin = duo(MapPin);
export const IconMicrophone = duo(Microphone);
export const IconEye = duo(Eye);
export const IconEyeSlash = duo(EyeSlash);
export const IconMinus = duo(Minus);
export const IconMinusCircle = duo(MinusCircle);
export const IconMonitor = duo(Monitor);
export const IconMoon = duo(Moon);
export const IconPaperclip = duo(Paperclip);
export const IconPaperPlaneTilt = duo(PaperPlaneTilt);
export const IconPencilSimple = duo(PencilSimple);
export const IconPlay = duo(Play);
export const IconPlus = duo(Plus);
export const IconQuestion = duo(Question);
export const IconBroadcast = duo(Broadcast);
export const IconRobot = duo(Robot);
export const IconRows = duo(Rows);
export const IconScan = duo(Scan);
export const IconSealCheck = duo(SealCheck);
export const IconShareNetwork = duo(ShareNetwork);
export const IconShieldCheck = duo(ShieldCheck);
export const IconSignOut = duo(SignOut);
export const IconSparkle = duo(Sparkle);
export const IconSpeakerHigh = duo(SpeakerHigh);
export const IconStop = duo(Stop);
export const IconSun = duo(Sun);
export const IconTextT = duo(TextT);
export const IconTimer = duo(Timer);
export const IconUsers = duo(Users);
export const IconVideoCamera = duo(VideoCamera);
export const IconWarning = duo(Warning);
export const IconWaveform = duo(Waveform);
export const IconWifiSlash = duo(WifiSlash);
export const IconX = duo(X);
export const IconXCircle = duo(XCircle);
export const IconAddressBook = duo(AddressBook);
export const IconCalculator = duo(Calculator);
export const IconCompass = duo(Compass);
export const IconNewspaper = duo(Newspaper);
export const IconRadio = duo(Radio);
export const IconStamp = duo(Stamp);
export const IconPhone = duo(Phone);
export const IconPrinter = duo(Printer);
