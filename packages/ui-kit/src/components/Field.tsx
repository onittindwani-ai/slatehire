"use client";
import { X } from "lucide-react";
import { useId, useRef, useState, type InputHTMLAttributes } from "react";
import { cn } from "../lib/cn";
import { Button } from "./Button";

export interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> {
  label: string;
  value: string;
  onChange: (v: string) => void;
  /** Return a message with the fix (for example "Add an @ and a domain") or null when valid. */
  validate?: (v: string) => string | null;
  hint?: string;
  maxLength?: number;
  clearable?: boolean;
}

/** Live validation after the first blur, inline error that says how to fix it, counter and clear button. */
export function Field({ label, value, onChange, validate, hint, maxLength, clearable, className, ...rest }: FieldProps) {
  const id = useId();
  const [touched, setTouched] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  const error = touched && validate ? validate(value) : null;
  return (
    <div className="sx-field">
      <label className="sx-label" htmlFor={id}>{label}</label>
      <div className="sx-input-wrap">
        <input
          {...rest}
          ref={ref}
          id={id}
          className={cn("sx-input", className)}
          value={value}
          maxLength={maxLength}
          aria-invalid={error ? true : undefined}
          aria-describedby={`${id}-d`}
          onBlur={() => setTouched(true)}
          onChange={(e) => onChange(e.target.value)}
        />
        {clearable && value ? (
          <Button
            icon size="sm" variant="ghost" feedback={false} className="sx-input-clear" aria-label={`Clear ${label}`}
            onClick={() => {
              onChange("");
              ref.current?.focus();
            }}
          >
            <X size={16} aria-hidden />
          </Button>
        ) : null}
      </div>
      <div className="sx-field__row" id={`${id}-d`}>
        {error ? <span className="sx-field__error" role="alert">{error}</span> : <span className="sx-field__hint">{hint}</span>}
        {maxLength ? <span className="sx-field__count sx-num">{value.length}/{maxLength}</span> : null}
      </div>
    </div>
  );
}
