import {memo,useState,type CSSProperties} from 'react';
import type {ProviderDriverKind} from '../../bridge/contracts';
import {OpenAI,ClaudeAI} from '../Icons';
import {cn} from '../../lib/utils';
const PROVIDER_ICON_BY_PROVIDER:Partial<Record<string,typeof OpenAI>>={codex:OpenAI,claudeAgent:ClaudeAI};
const providerInstanceInitials=(name:string)=>name.trim().split(/\s+/).slice(0,2).map(s=>s[0]??'').join('').toUpperCase();
export const ProviderInstanceIcon = memo(function ProviderInstanceIcon(props: {
  driverKind: ProviderDriverKind;
  displayName: string;
  accentColor?: string | undefined;
  acpRegistryAgentId?: string | undefined;
  acpRegistryIconUrl?: string | undefined;
  showBadge?: boolean;
  badgeContent?: "initials" | "none";
  className?: string;
  iconClassName?: string;
  badgeClassName?: string;
  statusDotClassName?: string;
  indicatorBackground?: string;
}) {
  const Icon = PROVIDER_ICON_BY_PROVIDER[props.driverKind] ?? null;
  const [failedIcon,setFailedIcon] = useState<string | null>(null);
  const packageIcon = props.acpRegistryIconUrl?.startsWith('https://') && failedIcon !== props.acpRegistryIconUrl ? props.acpRegistryIconUrl : null;
  const indicatorBackground = props.indicatorBackground ?? "var(--card)";
  const accentStyle = props.accentColor
    ? ({ "--provider-accent": props.accentColor } as CSSProperties)
    : undefined;
  const badgeContent = props.badgeContent ?? "initials";
  const isAcpRegistry = props.driverKind === "acpRegistry";


  return (
    <span
      className={cn(
        "relative isolate z-30 inline-flex shrink-0 items-center justify-center overflow-visible",
        props.className,
      )}
      style={accentStyle}
      data-provider-accent-color={props.accentColor}
    >
      {packageIcon ? <img src={packageIcon} alt="" referrerPolicy="no-referrer" className={cn("size-5 shrink-0",props.iconClassName)} onError={()=>setFailedIcon(packageIcon)}/> : Icon ? (
        <Icon className={cn("size-5 shrink-0", props.iconClassName)} aria-hidden />
      ) : (
        <span className={cn("text-3xs font-semibold leading-none", props.iconClassName)}>
          {providerInstanceInitials(props.displayName)}
        </span>
      )}
      {props.statusDotClassName ? (
        <span
          className={cn(
            "pointer-events-none absolute -left-0.5 -top-0.5 z-10 size-2 rounded-full",
            props.statusDotClassName,
          )}
          style={{ boxShadow: `0 0 0 2px ${indicatorBackground}` }}
          aria-hidden
        />
      ) : null}
      {props.showBadge ? (
        <span
          className={cn(
            "pointer-events-none absolute right-0 bottom-0 z-10 flex h-3.5 min-w-3.5 items-center justify-center rounded-full border px-0.5 text-4xs font-semibold leading-none shadow-sm",
            props.accentColor
              ? "bg-(--provider-accent) text-white"
              : "bg-card text-muted-foreground",
            props.badgeClassName,
          )}
          style={{ borderColor: indicatorBackground }}
          aria-hidden
        >
          {badgeContent === "initials" ? providerInstanceInitials(props.displayName) : null}
        </span>
      ) : null}
    </span>
  );
});
