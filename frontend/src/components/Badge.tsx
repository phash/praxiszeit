import { ReactNode } from 'react';
import { AbsenceType, ABSENCE_TYPE_BADGE_COLORS } from '../constants/absenceTypes';

type BadgeVariant = AbsenceType | 'success' | 'error' | 'warning' | 'info' | 'default';

interface BadgeProps {
  variant: BadgeVariant;
  children: ReactNode;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

const Badge = ({ variant, children, className = '', size = 'md' }: BadgeProps) => {
  const variantStyles: Record<BadgeVariant, string> = {
    ...ABSENCE_TYPE_BADGE_COLORS,
    success: 'bg-green-100 text-green-800',
    error: 'bg-red-100 text-red-800',
    warning: 'bg-yellow-100 text-yellow-800',
    info: 'bg-blue-100 text-blue-800',
    default: 'bg-gray-100 text-gray-800',
  };

  const sizeStyles = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-0.5 text-xs',
    lg: 'px-3 py-1 text-sm',
  };

  return (
    <span
      className={`
        inline-flex items-center font-medium rounded-full
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        ${className}
      `}
    >
      {children}
    </span>
  );
};

export default Badge;
