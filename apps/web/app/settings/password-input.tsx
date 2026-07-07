"use client";

import { Eye, EyeOff } from "lucide-react";
import { MouseEvent, PointerEvent, useRef, useState } from "react";

export function PasswordInput({ defaultValue }: { defaultValue: string }) {
  const [visible, setVisible] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function keepInputFocus(event: PointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
  }

  function toggle(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    const next = !visible;
    setVisible(next);
    if (inputRef.current) {
      inputRef.current.type = next ? "text" : "password";
      inputRef.current.focus();
    }
  }

  return (
    <div className="passwordField">
      <input
        id="database-password"
        ref={inputRef}
        name="password"
        type={visible ? "text" : "password"}
        defaultValue={defaultValue}
        placeholder="Postgres password"
      />
      <button
        type="button"
        aria-label={visible ? "Hide password" : "Show password"}
        title={visible ? "Hide password" : "Show password"}
        onPointerDown={keepInputFocus}
        onClick={toggle}
      >
        {visible ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}
