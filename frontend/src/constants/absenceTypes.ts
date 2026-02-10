export type AbsenceType = 'vacation' | 'sick' | 'training' | 'other';

export const ABSENCE_TYPE_LABELS: Record<AbsenceType, string> = {
  vacation: 'Urlaub',
  sick: 'Krank',
  training: 'Fortbildung',
  other: 'Sonstiges',
};

export const ABSENCE_TYPE_COLORS: Record<AbsenceType, string> = {
  vacation: 'bg-blue-100 text-blue-800 border-blue-300',
  sick: 'bg-red-100 text-red-800 border-red-300',
  training: 'bg-orange-100 text-orange-800 border-orange-300',
  other: 'bg-gray-100 text-gray-800 border-gray-300',
};

export const ABSENCE_TYPE_BADGE_COLORS: Record<AbsenceType, string> = {
  vacation: 'bg-blue-100 text-blue-800',
  sick: 'bg-red-100 text-red-800',
  training: 'bg-orange-100 text-orange-800',
  other: 'bg-gray-100 text-gray-800',
};

export const ABSENCE_TYPE_DOT_COLORS: Record<AbsenceType, string> = {
  vacation: 'bg-blue-500',
  sick: 'bg-red-500',
  training: 'bg-orange-500',
  other: 'bg-gray-500',
};
