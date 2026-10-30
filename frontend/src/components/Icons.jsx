// Minimal inline stroke icons, so the app has no icon-library dependency.
const base = {
  width: 16,
  height: 16,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

const make = (paths) =>
  function Icon({ className = "", size = 16, ...rest }) {
    return (
      <svg {...base} width={size} height={size} className={className} aria-hidden="true" {...rest}>
        {paths}
      </svg>
    );
  };

export const PlusIcon = make(<path d="M12 5v14M5 12h14" />);
export const CheckIcon = make(<path d="M5 12.5l4.5 4.5L19 7.5" />);
export const UndoIcon = make(<path d="M9 14L4 9l5-5M4 9h10.5a5.5 5.5 0 010 11H11" />);
export const TrashIcon = make(
  <>
    <path d="M4 7h16M10 11v6M14 11v6" />
    <path d="M6 7l1 12a2 2 0 002 2h6a2 2 0 002-2l1-12M9 7V4h6v3" />
  </>
);
export const StarIcon = make(
  <path d="M12 3.5l2.6 5.3 5.9.9-4.25 4.1 1 5.8L12 16.9l-5.25 2.7 1-5.8L3.5 9.7l5.9-.9z" />
);
export const LinkIcon = make(
  <>
    <path d="M10 14a4 4 0 005.66 0l3-3a4 4 0 00-5.66-5.66l-1 1" />
    <path d="M14 10a4 4 0 00-5.66 0l-3 3a4 4 0 005.66 5.66l1-1" />
  </>
);
export const ExternalIcon = make(<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5" />);
export const NoteIcon = make(
  <>
    <path d="M5 4h10l4 4v12H5z" />
    <path d="M15 4v4h4M8 12h8M8 16h5" />
  </>
);
export const SparkIcon = make(
  <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6" />
);
export const RefreshIcon = make(<path d="M20 11a8 8 0 10-2.3 5.7M20 4v7h-7" />);
export const XIcon = make(<path d="M6 6l12 12M18 6L6 18" />);
export const BookIcon = make(
  <>
    <path d="M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2z" />
    <path d="M4 19V5M9 7h6" />
  </>
);
export const ArchiveIcon = make(
  <>
    <path d="M3 4h18v4H3zM5 8v11a1 1 0 001 1h12a1 1 0 001-1V8" />
    <path d="M10 12h4" />
  </>
);
export const SearchIcon = make(
  <>
    <circle cx="11" cy="11" r="6.5" />
    <path d="M20 20l-4.2-4.2" />
  </>
);
export const BellIcon = make(
  <>
    <path d="M6 16V11a6 6 0 1112 0v5l1.5 2h-15z" />
    <path d="M10 21h4" />
  </>
);
export const PinIcon = make(<path d="M9 4h6l-1 6 3 3H7l3-3zM12 13v8" />);
export const UploadIcon = make(<path d="M12 16V4M7 9l5-5 5 5M5 20h14" />);
export const ImageIcon = make(
  <>
    <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
    <circle cx="9" cy="10" r="1.6" />
    <path d="M20.5 16l-5-5-8 8.5" />
  </>
);
export const FileIcon = make(
  <>
    <path d="M6 3h9l4 4v14H6z" />
    <path d="M14 3v5h5" />
  </>
);
export const CodeIcon = make(<path d="M9 8l-4 4 4 4M15 8l4 4-4 4" />);
export const QuoteIcon = make(<path d="M7 17c-1.7 0-3-1.3-3-3 0-3 2-6 5-7M16 17c-1.7 0-3-1.3-3-3 0-3 2-6 5-7" />);
export const ArrowIcon = make(<path d="M5 12h14M13 6l6 6-6 6" />);
export const AlertIcon = make(
  <>
    <path d="M12 4l9 16H3z" />
    <path d="M12 10v4M12 17v.5" />
  </>
);
