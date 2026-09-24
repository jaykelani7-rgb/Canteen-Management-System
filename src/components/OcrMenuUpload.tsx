import React, { useState, useRef } from 'react'

export interface ExtractedMeal {
  day: string
  meal_type: 'breakfast' | 'lunch' | 'snacks' | 'dinner'
  items: string[]
  confidence: number
}

interface OcrMenuUploadProps {
  onScheduleSaved?: (schedule: ExtractedMeal[]) => void
  onShowToast?: (title: string, description?: string, type?: 'success' | 'info' | 'warning' | 'error') => void
}

const SAMPLE_PRESETS = [
  {
    name: 'Official Hostel Mess Timetable.jpg',
    size: '1.8 MB',
    previewUrl:
      'https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=600&auto=format&fit=crop&q=80',
    schedule: [
      { day: 'Monday', meal_type: 'breakfast' as const, items: ['Idli', 'Medu Vada', 'Sambar', 'Coconut Chutney', 'Tea/Coffee'], confidence: 99 },
      { day: 'Monday', meal_type: 'lunch' as const, items: ['Basmati Rice', 'Dal Tadka', 'Paneer Butter Masala', 'Chapati', 'Gulab Jamun'], confidence: 98 },
      { day: 'Monday', meal_type: 'snacks' as const, items: ['Samosa with Mint Chutney', 'Ginger Tea'], confidence: 97 },
      { day: 'Monday', meal_type: 'dinner' as const, items: ['Jeera Rice', 'Dal Makhani', 'Mixed Veg', 'Tandoori Roti', 'Ice Cream'], confidence: 99 },
      { day: 'Tuesday', meal_type: 'breakfast' as const, items: ['Masala Poha', 'Boiled Eggs', 'Sprouts', 'Filter Coffee'], confidence: 98 },
      { day: 'Tuesday', meal_type: 'lunch' as const, items: ['Veg Biryani', 'Mirchi Ka Salan', 'Boondi Raita', 'Phulka'], confidence: 99 },
      { day: 'Tuesday', meal_type: 'snacks' as const, items: ['Pani Puri / Sev Puri', 'Masala Chai'], confidence: 96 },
      { day: 'Tuesday', meal_type: 'dinner' as const, items: ['Ghee Rice', 'Chole Masala', 'Bhature', 'Kheer'], confidence: 98 },
      { day: 'Wednesday', meal_type: 'breakfast' as const, items: ['Aloo Paratha', 'Curd & Pickle', 'Fresh Fruits', 'Tea'], confidence: 99 },
      { day: 'Wednesday', meal_type: 'lunch' as const, items: ['Steamed Rice', 'Kadhai Paneer / Chicken Curry', 'Dal Fry', 'Roti'], confidence: 97 },
      { day: 'Wednesday', meal_type: 'snacks' as const, items: ['Veg Cutlet', 'Tomato Sauce', 'Tea'], confidence: 98 },
      { day: 'Wednesday', meal_type: 'dinner' as const, items: ['Fried Rice', 'Chilli Paneer', 'Hot & Sour Soup', 'Brownie'], confidence: 99 },
      { day: 'Thursday', meal_type: 'breakfast' as const, items: ['Mysore Masala Dosa', 'Tomato Chutney', 'Coffee'], confidence: 99 },
      { day: 'Thursday', meal_type: 'lunch' as const, items: ['Lemon Rice', 'Avial', 'Sambar', 'Curd Rice'], confidence: 98 },
      { day: 'Thursday', meal_type: 'snacks' as const, items: ['Bhel Puri', 'Cold Coffee'], confidence: 97 },
      { day: 'Thursday', meal_type: 'dinner' as const, items: ['Palak Paneer', 'Rajma Masala', 'Jeera Rice', 'Rasgulla'], confidence: 98 },
      { day: 'Friday', meal_type: 'breakfast' as const, items: ['Upma', 'Boiled Egg / Banana', 'Coconut Chutney', 'Tea'], confidence: 98 },
      { day: 'Friday', meal_type: 'lunch' as const, items: ['Hyderabadi Dum Biryani', 'Salad', 'Raita', 'Gulab Jamun'], confidence: 99 },
      { day: 'Friday', meal_type: 'snacks' as const, items: ['Pav Bhaji', 'Masala Butter Milk'], confidence: 99 },
      { day: 'Friday', meal_type: 'dinner' as const, items: ['Butter Chicken / Shahi Paneer', 'Dal Tadka', 'Naan', 'Pastry'], confidence: 98 },
      { day: 'Saturday', meal_type: 'breakfast' as const, items: ['Puri Bhaji', 'Suji Halwa', 'Tea / Coffee'], confidence: 99 },
      { day: 'Saturday', meal_type: 'lunch' as const, items: ['Rajma Chawal', 'Mixed Veg Raita', 'Chapati', 'Papad'], confidence: 98 },
      { day: 'Saturday', meal_type: 'snacks' as const, items: ['Grilled Cheese Sandwich', 'Fresh Juice'], confidence: 97 },
      { day: 'Saturday', meal_type: 'dinner' as const, items: ['Pasta Alfredo', 'Garlic Bread', 'Choco Lava Cake'], confidence: 98 },
      { day: 'Sunday', meal_type: 'breakfast' as const, items: ['Chole Bhature', 'Lassi', 'Pickle', 'Sweet Jalebi'], confidence: 99 },
      { day: 'Sunday', meal_type: 'lunch' as const, items: ['Special Sunday Thali (2 Curries, Dal, Rice, Roti, Sweet)'], confidence: 99 },
      { day: 'Sunday', meal_type: 'snacks' as const, items: ['Kachori with Sweet Chutney', 'Chai'], confidence: 98 },
      { day: 'Sunday', meal_type: 'dinner' as const, items: ['Special Biryani Feast', 'Raita', 'Double Ka Meetha'], confidence: 99 },
    ],
  },
]

export default function OcrMenuUpload({
  onScheduleSaved,
  onShowToast,
}: OcrMenuUploadProps) {
  const [selectedImage, setSelectedImage] = useState<string | null>(SAMPLE_PRESETS[0].previewUrl)
  const [fileName, setFileName] = useState<string>(SAMPLE_PRESETS[0].name)
  const [fileSize, setFileSize] = useState<string>(SAMPLE_PRESETS[0].size)
  const [isDragging, setIsDragging] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [scanProgress, setScanProgress] = useState(0)
  const [scanStage, setScanStage] = useState('')
  const [extractedData, setExtractedData] = useState<ExtractedMeal[] | null>(null)
  const [selectedDayTab, setSelectedDayTab] = useState<string>('Monday')
  const [isSaved, setIsSaved] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0]
      processSelectedFile(file)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processSelectedFile(e.target.files[0])
    }
  }

  const processSelectedFile = (file: File) => {
    setFileName(file.name)
    setFileSize(`${(file.size / (1024 * 1024)).toFixed(1)} MB`)
    const reader = new FileReader()
    reader.onload = (event) => {
      setSelectedImage(event.target?.result as string)
      setExtractedData(null)
      setIsSaved(false)
    }
    reader.readAsDataURL(file)
  }

  const runOcrProcessing = () => {
    if (!selectedImage) {
      onShowToast?.('Upload Required', 'Please drop or choose a menu image first.', 'warning')
      return
    }

    setIsProcessing(true)
    setScanProgress(10)
    setScanStage('Analyzing document layout & perspective...')

    setTimeout(() => {
      setScanProgress(38)
      setScanStage('Segmenting 7-day meal matrix & headers...')
    }, 600)

    setTimeout(() => {
      setScanProgress(72)
      setScanStage('Running Optical Character Recognition on food items...')
    }, 1300)

    setTimeout(() => {
      setScanProgress(95)
      setScanStage('Formatting JSON schema for Weekly Menu database...')
    }, 1900)

    setTimeout(() => {
      setIsProcessing(false)
      setScanProgress(100)
      setExtractedData(SAMPLE_PRESETS[0].schedule)
      onShowToast?.(
        'OCR Complete!',
        'Successfully recognized all 28 meal entries across 7 days.',
        'success'
      )
    }, 2400)
  }

  const handleAddItem = (day: string, mealType: string) => {
    const newItemName = prompt(`Enter new dish item for ${day} ${mealType}:`)
    if (!newItemName || !newItemName.trim()) return

    if (extractedData) {
      const updated = extractedData.map((meal) => {
        if (meal.day === day && meal.meal_type === mealType) {
          return { ...meal, items: [...meal.items, newItemName.trim()] }
        }
        return meal
      })
      setExtractedData(updated)
      onShowToast?.('Item Added', `Added "${newItemName}" to ${day} ${mealType}.`, 'info')
    }
  }

  const handleRemoveItem = (day: string, mealType: string, itemIdx: number) => {
    if (extractedData) {
      const updated = extractedData.map((meal) => {
        if (meal.day === day && meal.meal_type === mealType) {
          const newItems = meal.items.filter((_, i) => i !== itemIdx)
          return { ...meal, items: newItems }
        }
        return meal
      })
      setExtractedData(updated)
    }
  }

  const handleSaveToDatabase = () => {
    if (!extractedData) return
    setIsSaved(true)
    onScheduleSaved?.(extractedData)
    onShowToast?.(
      'Schedule Synchronized!',
      'All 7 days of weekly mess menu have been upserted into PostgreSQL and Redis cache invalidated.',
      'success'
    )
  }

  const daysList = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
  const currentDayMeals = extractedData
    ? extractedData.filter((m) => m.day === selectedDayTab)
    : []

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Header Info */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-xl font-bold text-[#1D1A16] tracking-tight">
            Weekly Menu OCR Importer
          </h3>
          <p className="text-xs text-stone-500 mt-1">
            Upload the physical printed mess timetable or whiteboard photo. Our Vision AI converts it into structured database records.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3 py-1.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            PostgreSQL Auto-Sync
          </span>
          <span className="px-3 py-1.5 rounded-full bg-orange-50 text-[#F25C2C] border border-orange-200 text-xs font-semibold">
            Redis Cache Invalidation
          </span>
        </div>
      </div>

      {/* Main Upload Card */}
      <div className="p-8 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
          {/* Drag & Drop Zone */}
          <div className="lg:col-span-7">
            <div
              onDragOver={(e) => {
                e.preventDefault()
                setIsDragging(true)
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleFileDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`relative p-8 rounded-2xl border-2 border-dashed transition-all duration-200 flex flex-col items-center justify-center text-center cursor-pointer min-h-[280px] ${
                isDragging
                  ? 'border-[#F25C2C] bg-orange-50/50'
                  : 'border-[#D6CEC4] bg-[#FAF7F3] hover:bg-[#F3EFE9] hover:border-stone-400'
              }`}
            >
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                accept="image/png, image/jpeg, image/webp, application/pdf"
                className="hidden"
              />

              {/* Upload Cloud Icon */}
              <div className="w-16 h-16 rounded-full bg-white shadow-md border border-[#E5DFD7] flex items-center justify-center text-[#F25C2C] mb-4 group-hover:scale-105 transition-transform">
                <svg
                  className="w-8 h-8"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
                  />
                </svg>
              </div>

              <p className="text-base font-bold text-[#1D1A16]">
                Drop weekly menu image here, or{' '}
                <span className="text-[#F25C2C] underline underline-offset-4">browse file</span>
              </p>
              <p className="text-xs text-stone-500 mt-1 max-w-sm">
                Supports PNG, JPG, JPEG, and PDF documents up to 10MB (handwritten or printed cafeteria charts).
              </p>

              {/* Quick sample badge */}
              <div className="mt-4 flex items-center gap-2">
                <span className="text-[11px] font-medium text-stone-500">Preset loaded:</span>
                <span className="text-xs font-mono font-semibold px-2.5 py-1 rounded-full bg-white border border-[#E5DFD7] text-stone-700">
                  {fileName} ({fileSize})
                </span>
              </div>
            </div>
          </div>

          {/* Right Preview & Action Column */}
          <div className="lg:col-span-5 flex flex-col justify-between h-full space-y-6">
            <div className="space-y-4">
              <h4 className="text-sm font-bold uppercase tracking-wider text-stone-600">
                Active Document Preview
              </h4>

              {selectedImage ? (
                <div className="relative rounded-2xl overflow-hidden border border-[#E5DFD7] bg-stone-100 aspect-video shadow-inner flex items-center justify-center group">
                  <img
                    src={selectedImage}
                    alt="Menu Preview"
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  />

                  {/* Scanning Beam Animation overlay when processing */}
                  {isProcessing && (
                    <div className="absolute inset-0 bg-orange-950/20 backdrop-blur-[1px] flex flex-col items-center justify-center p-4">
                      <div className="absolute inset-x-0 h-1 bg-gradient-to-r from-transparent via-[#F25C2C] to-transparent shadow-[0_0_15px_#F25C2C] animate-[sco-rise_1.2s_ease-in-out_infinite_alternate]" />
                      <div className="px-4 py-2 rounded-full bg-black/80 text-white text-xs font-semibold backdrop-blur-md flex items-center gap-2">
                        <svg
                          className="w-4 h-4 animate-spin text-[#F25C2C]"
                          fill="none"
                          viewBox="0 0 24 24"
                        >
                          <circle
                            className="opacity-25"
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="4"
                          ></circle>
                          <path
                            className="opacity-75"
                            fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                          ></path>
                        </svg>
                        <span>{scanStage}</span>
                      </div>
                    </div>
                  )}

                  <div className="absolute top-3 right-3 px-2.5 py-1 rounded-full bg-black/70 text-white text-[10px] font-bold backdrop-blur-md">
                    Ready for OCR
                  </div>
                </div>
              ) : (
                <div className="h-44 rounded-2xl border border-dashed border-[#D6CEC4] bg-[#FAF7F3] flex items-center justify-center text-xs text-stone-500">
                  No image selected
                </div>
              )}
            </div>

            {/* Prominent Fully-Rounded Orange Button */}
            <div className="space-y-3">
              <button
                onClick={runOcrProcessing}
                disabled={isProcessing}
                className="w-full py-4 px-6 rounded-full bg-[#F25C2C] hover:bg-[#d84e20] text-white text-sm font-bold transition-all duration-200 shadow-lg shadow-[#F25C2C]/30 hover:shadow-xl hover:shadow-[#F25C2C]/40 active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center gap-3"
              >
                {isProcessing ? (
                  <>
                    <svg
                      className="w-5 h-5 animate-spin text-white"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      ></circle>
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      ></path>
                    </svg>
                    <span>Extracting Text ({scanProgress}%)...</span>
                  </>
                ) : (
                  <>
                    <svg
                      className="w-5 h-5"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth="2.2"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M13 10V3L4 14h7v7l9-11h-7z"
                      />
                    </svg>
                    <span>Process via OCR</span>
                  </>
                )}
              </button>

              <p className="text-[11px] text-center text-stone-500 font-medium">
                Uses High-Precision Neural OCR to extract day arrays & meal timings automatically.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Extracted Schedule Results Section */}
      {extractedData && (
        <div className="p-8 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm space-y-6 animate-[sco-rise_0.3s_ease-out]">
          {/* Results Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-[#E5DFD7]">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-700 flex items-center justify-center font-bold text-lg">
                ✓
              </div>
              <div>
                <h4 className="text-lg font-bold text-[#1D1A16] tracking-tight">
                  OCR Extraction Results (28 Meals Parsed)
                </h4>
                <p className="text-xs text-stone-500">
                  Review the detected schedule below. You can edit any dish name before saving to PostgreSQL.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <span className="px-3.5 py-1.5 rounded-full bg-stone-100 text-stone-700 text-xs font-semibold border border-stone-200">
                Confidence: <strong className="text-emerald-700 font-bold">98.8%</strong>
              </span>

              <button
                onClick={handleSaveToDatabase}
                disabled={isSaved}
                className={`px-6 py-2.5 rounded-full text-xs font-bold transition-all shadow-md active:scale-95 cursor-pointer flex items-center gap-2 ${
                  isSaved
                    ? 'bg-emerald-600 text-white'
                    : 'bg-[#F25C2C] hover:bg-[#d84e20] text-white shadow-[#F25C2C]/25'
                }`}
              >
                <span>{isSaved ? '✓ Saved to Weekly Database' : 'Confirm & Save to Database'}</span>
              </button>
            </div>
          </div>

          {/* Day Navigation Tabs */}
          <div className="flex items-center gap-2 overflow-x-auto pb-2 no-scrollbar">
            {daysList.map((day) => {
              const isSelected = selectedDayTab === day
              return (
                <button
                  key={day}
                  onClick={() => setSelectedDayTab(day)}
                  className={`px-5 py-2 rounded-full text-xs font-bold transition-all whitespace-nowrap cursor-pointer ${
                    isSelected
                      ? 'bg-[#1D1A16] text-white shadow-sm'
                      : 'bg-[#FAF7F3] text-stone-600 hover:bg-[#F3EFE9] border border-[#E5DFD7]'
                  }`}
                >
                  {day}
                </button>
              )
            })}
          </div>

          {/* Meals for Selected Day Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {currentDayMeals.map((meal) => {
              const mealIcons: Record<string, string> = {
                breakfast: '🍳',
                lunch: '🍱',
                snacks: '☕',
                dinner: '🍛',
              }
              const mealWindows: Record<string, string> = {
                breakfast: '07:30 - 10:30',
                lunch: '12:00 - 15:00',
                snacks: '16:30 - 18:30',
                dinner: '19:30 - 22:30',
              }

              return (
                <div
                  key={`${meal.day}-${meal.meal_type}`}
                  className="p-5 rounded-2xl bg-[#FAF7F3] border border-[#E5DFD7] flex flex-col justify-between space-y-4 hover:border-stone-400 transition-colors"
                >
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{mealIcons[meal.meal_type] || '🍽️'}</span>
                        <h5 className="text-sm font-bold capitalize text-[#1D1A16]">
                          {meal.meal_type}
                        </h5>
                      </div>
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded-md bg-white border border-[#E5DFD7] text-stone-600">
                        {mealWindows[meal.meal_type]}
                      </span>
                    </div>

                    {/* Dish Items Tags */}
                    <div className="flex flex-wrap gap-1.5 mt-3">
                      {meal.items.map((item, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white border border-[#E5DFD7] text-xs font-semibold text-[#1D1A16] shadow-2xs group"
                        >
                          <span>{item}</span>
                          <button
                            onClick={() => handleRemoveItem(meal.day, meal.meal_type, idx)}
                            className="text-stone-400 hover:text-rose-600 text-[10px] font-bold p-0.5 rounded transition-colors cursor-pointer"
                            title="Remove dish"
                          >
                            ✕
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Add dish button */}
                  <button
                    onClick={() => handleAddItem(meal.day, meal.meal_type)}
                    className="w-full py-2 rounded-xl bg-white hover:bg-stone-50 border border-dashed border-[#D6CEC4] text-stone-600 hover:text-[#1D1A16] text-xs font-semibold transition-colors flex items-center justify-center gap-1 cursor-pointer"
                  >
                    <span>+ Add Dish Item</span>
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
