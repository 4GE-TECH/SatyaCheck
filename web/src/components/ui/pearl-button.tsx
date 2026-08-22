import React from "react";

export type PearlButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  label?: string;
  children?: React.ReactNode;
};

export const PearlButton: React.FC<PearlButtonProps> = ({
  label = "Pearl Button",
  children,
  className = "",
  ...props
}) => {
  return (
    <>
      <style>{`
        .pearl-button {
          --white: #ffe7ff;
          --bg: #080808;
          --text-color: rgba(255, 255, 255, 0.9);
          --radius: 100px;
          outline: none;
          cursor: pointer;
          border: 0;
          position: relative;
          border-radius: var(--radius);
          background-color: var(--bg);
          transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
          box-shadow:
            inset 0 0.3rem 0.9rem rgba(255, 255, 255, 0.25),
            inset 0 -0.1rem 0.3rem rgba(0, 0, 0, 0.7),
            inset 0 -0.4rem 0.9rem rgba(255, 255, 255, 0.35),
            0 1.5rem 2rem -0.5rem rgba(0, 0, 0, 0.5),
            0 0.5rem 1rem -0.3rem rgba(0, 0, 0, 0.8);
        }

        /* Light mode support */
        html:not(.dark) .pearl-button {
          --bg: #FFFFFF;
          --text-color: #0F172A;
          box-shadow:
            inset 0 0.2rem 0.6rem rgba(255, 255, 255, 0.9),
            inset 0 -0.1rem 0.3rem rgba(0, 0, 0, 0.08),
            inset 0 -0.4rem 0.8rem rgba(0, 0, 0, 0.06),
            0 1rem 1.5rem -0.5rem rgba(0, 0, 0, 0.15),
            0 0.4rem 0.6rem -0.2rem rgba(0, 0, 0, 0.1);
          border: 1px solid rgba(0, 0, 0, 0.08);
        }

        .pearl-button .wrap {
          font-size: 16px;
          font-weight: 600;
          color: var(--text-color);
          padding: 16px 28px;
          border-radius: inherit;
          position: relative;
          overflow: hidden;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .pearl-button .wrap p span:nth-child(2) {
          display: none;
        }
        .pearl-button:hover .wrap p span:nth-child(1) {
          display: none;
        }
        .pearl-button:hover .wrap p span:nth-child(2) {
          display: inline-block;
        }

        .pearl-button .wrap p {
          display: flex;
          align-items: center;
          gap: 10px;
          margin: 0;
          transition: all 0.2s ease;
          transform: translateY(1%);
        }

        .pearl-button .wrap::before,
        .pearl-button .wrap::after {
          content: "";
          position: absolute;
          transition: all 0.3s ease;
          pointer-events: none;
        }

        .pearl-button .wrap::before {
          left: -15%;
          right: -15%;
          bottom: 25%;
          top: -100%;
          border-radius: 50%;
          background-color: rgba(255, 255, 255, 0.12);
        }

        html:not(.dark) .pearl-button .wrap::before {
          background-color: rgba(0, 0, 0, 0.03);
        }

        .pearl-button .wrap::after {
          left: 6%;
          right: 6%;
          top: 10%;
          bottom: 40%;
          border-radius: 22px 22px 0 0;
          box-shadow: inset 0 10px 8px -10px rgba(255, 255, 255, 0.8);
          background: linear-gradient(
            180deg,
            rgba(255, 255, 255, 0.3) 0%,
            rgba(0, 0, 0, 0) 50%,
            rgba(0, 0, 0, 0) 100%
          );
        }

        html:not(.dark) .pearl-button .wrap::after {
          box-shadow: inset 0 10px 8px -10px rgba(255, 255, 255, 1);
          background: linear-gradient(
            180deg,
            rgba(255, 255, 255, 0.8) 0%,
            rgba(255, 255, 255, 0) 100%
          );
        }

        .pearl-button:hover {
          box-shadow:
            inset 0 0.3rem 0.6rem rgba(255, 255, 255, 0.4),
            inset 0 -0.1rem 0.3rem rgba(0, 0, 0, 0.7),
            inset 0 -0.4rem 0.9rem rgba(255, 255, 255, 0.5),
            0 1.8rem 2.5rem -0.5rem rgba(0, 0, 0, 0.6),
            0 0.6rem 1rem -0.3rem rgba(0, 0, 0, 0.9);
          transform: translateY(-1px);
        }

        html:not(.dark) .pearl-button:hover {
          box-shadow:
            inset 0 0.2rem 0.6rem rgba(255, 255, 255, 1),
            inset 0 -0.1rem 0.3rem rgba(0, 0, 0, 0.05),
            inset 0 -0.4rem 0.8rem rgba(0, 0, 0, 0.08),
            0 1.2rem 1.8rem -0.5rem rgba(0, 0, 0, 0.2),
            0 0.5rem 0.8rem -0.2rem rgba(0, 0, 0, 0.12);
        }

        .pearl-button:hover .wrap::before {
          transform: translateY(-5%);
        }
        .pearl-button:hover .wrap::after {
          opacity: 0.5;
          transform: translateY(3%);
        }
        .pearl-button:hover .wrap p {
          transform: translateY(-2%);
        }
        .pearl-button:active {
          transform: translateY(2px);
          box-shadow:
            inset 0 0.3rem 0.5rem rgba(255, 255, 255, 0.5),
            inset 0 -0.1rem 0.3rem rgba(0, 0, 0, 0.8),
            inset 0 -0.4rem 0.9rem rgba(255, 255, 255, 0.3),
            0 1rem 1.5rem -0.5rem rgba(0, 0, 0, 0.4),
            0 0.4rem 0.8rem -0.3rem rgba(0, 0, 0, 0.7);
        }
      `}</style>

      <button className={`pearl-button ${className}`} {...props}>
        <div className="wrap">
          <p>
            <span>✧</span>
            <span>✦</span>
            {children || label}
          </p>
        </div>
      </button>
    </>
  );
};

export default PearlButton;
