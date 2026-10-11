import type {ComponentPropsWithoutRef, ReactNode} from 'react';
import {cn} from '../../lib/utils';
import {SettingsGroup} from './SettingsGroup';
export function SettingsSection({
  title,
  hideTitle = false,
  icon,
  titleAction,
  headerAction,
  variant = "grouped",
  children,
  className,
  ...sectionProps
}: ComponentPropsWithoutRef<"section"> & {
  title: string;
  hideTitle?: boolean;
  icon?: ReactNode;
  /** Small control shown right after the title, such as an add button. */
  titleAction?: ReactNode;
  headerAction?: ReactNode;
  variant?: "grouped" | "plain";
  children: ReactNode;
}) {


  return (
    <section
      {...sectionProps}
      tabIndex={sectionProps.id ? -1 : sectionProps.tabIndex}
      className={cn(!hideTitle && "space-y-2.5", className)}
    >
      {hideTitle ? (
        <h2 className="sr-only">{title}</h2>
      ) : (
        <div
          data-settings-scroll-target
          className="flex min-h-7 items-start justify-between gap-4 px-3 sm:px-4"
        >
          <div className="flex min-w-0 items-center gap-1">
            <h2 className="flex min-h-7 items-center gap-2 text-sm font-normal text-foreground/70">
              {icon}
              {title}
            </h2>
            {titleAction}
          </div>
          <div className="flex min-h-7 min-w-7 items-center justify-end">{headerAction}</div>
        </div>
      )}
      <SettingsGroup data-settings-scroll-target={hideTitle ? "" : undefined} variant={variant}>
        {children}
      </SettingsGroup>
    </section>
  );
}

export function SettingsRow({title,description,status:renderedStatus,resetAction:renderedReset,control:renderedControl,children,className,...rowProps}: Omit<ComponentPropsWithoutRef<'div'>,'title'> & {title:ReactNode;description?:ReactNode;status?:ReactNode;resetAction?:ReactNode;control?:ReactNode;children?:ReactNode}) {
 const renderedInheritance=null, unavailable=false;
  return (
    <div
      {...rowProps}
      tabIndex={rowProps.id ? -1 : rowProps.tabIndex}
      data-slot="settings-row"
      className={cn(
        "@container/settings-row rounded-xl px-3 sm:px-4 aria-disabled:opacity-64 aria-disabled:[&_*]:text-muted-foreground",
        children ? "pt-3 pb-1" : "py-3",
        className,
      )}
    >
      <div className="flex flex-col gap-3 @min-[32rem]/settings-row:grid @min-[32rem]/settings-row:grid-cols-[minmax(0,1fr)_minmax(10rem,auto)] @min-[32rem]/settings-row:items-center @min-[32rem]/settings-row:gap-8">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex min-h-5 items-center gap-1.5">
            <h3 className="text-sm font-medium text-foreground">{title}</h3>
            {renderedInheritance ? (
              <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center">
                {renderedInheritance}
              </span>
            ) : null}
            <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center">
              {renderedReset}
            </span>
          </div>
          {description ? (
            <p className="max-w-xl text-xs leading-normal text-muted-foreground/80">
              {description}
            </p>
          ) : null}
          {renderedStatus ? (
            <div className="pt-0.5 text-xs text-muted-foreground">{renderedStatus}</div>
          ) : null}
        </div>
        {renderedControl ? (
          <div className="flex w-full min-w-0 shrink-0 items-center gap-2 @min-[32rem]/settings-row:w-auto @min-[32rem]/settings-row:justify-end">
            {renderedControl}
          </div>
        ) : null}
      </div>
      {unavailable && children ? (
        <div inert className="opacity-50">
          {children}
        </div>
      ) : (
        children
      )}
    </div>
  );
}
