export interface CardEntry {
  quantity: int;
  name: string;
  set_code: string;
  collector_number: string;
  raw_line: string;
}

export interface PrintSettings {
  card_width_mm: number;
  card_height_mm: number;
  corner_radius_mm: number;
  padding_mm: number;
  output_format: 'pdf' | 'png';
  is_transformer: boolean;
}

export interface PywebviewApi {
  // Downloader
  start_download(order_name: string, card_list_text: string, include_tokens?: boolean, dual_face_token?: boolean): Promise<void>;
  get_error_cards(order_name: string): Promise<string[]>;
  
  // Print Setup
  get_default_settings(): Promise<PrintSettings>;
  browse_folder(): Promise<string>;
  create_output(
    image_folder: string,
    card_width: number,
    card_height: number,
    corner_radius: number,
    padding: number,
    output_format: string,
    is_transformer: boolean
  ): Promise<void>;

  // Card Lookup
  autocomplete_card(query: string): Promise<string[]>;
  search_card(name: string): Promise<any[]>;
  lookup_card(set_code: string, collector_number: string): Promise<any[]>;
  download_single_card(card_data: any, quantity: number, folder: string): Promise<void>;
}

declare global {
  interface Window {
    pywebview: {
      api: PywebviewApi;
    };
    __pushLog?: (level: string, message: string) => void;
    __pushProgress?: (current: number, total: number, label: string) => void;
    __onTaskComplete?: (result: any) => void;
  }
}
