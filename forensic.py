import sys
import struct
import os
import shutil


class FAT:
    # This class represents a FAT (File Allocation Table) filesystem.

    def getSector(self, sector: int) -> bytes:
        # This method reads a sector of data from the FAT image file.
        self.fatFile.seek(sector * self.BytsPerSec)
        return self.fatFile.read(self.BytsPerSec)

    def read_fat_entry(self, cluster):
        # This method reads an entry from the FAT table corresponding to the given cluster.

        # Calculate the sector number within the FAT table where the cluster entry is located.
        fat_sector_number = self.FATStart + (cluster // 256)

        # Read the entire sector containing the FAT entry for the given cluster.
        fat_sector = self.getSector(fat_sector_number)

        # Calculate the offset of the cluster entry within the sector.
        entry_offset = cluster % 256

        # Extract the 2-byte entry from the sector data and interpret it as an unsigned short integer.
        next_cluster = struct.unpack("<H", fat_sector[entry_offset * 2:entry_offset * 2 + 2])[0]

        # Return the value of the next cluster in the chain.
        return next_cluster

    def __init__(self, imageFileName: str) -> None:
        # The constructor initializes the FAT object with the given FAT image file name.

        # Open the FAT image file in binary read mode.
        self.fatFile = open(imageFileName, 'rb')

        # Set the number of bytes per sector to 512. This value is commonly used in FAT16.
        self.BytsPerSec = 512

        # Read the first sector (boot sector) of the FAT image file.
        block0 = self.getSector(0)

        # Unpack the boot sector fields using the struct module.
        # This line extracts the values of the various fields in the boot sector and assigns them to instance variables.
        self.jmpBoot, self.OemName, self.BytsPerSec, self.SecPerClus, \
        self.ResvdSecCnt, self.NumFATs, self.RootEntCnt, \
        self.TotSec16, self.Media, self.FATSz16, self.SecPerTrk, \
        self.NumHeads, self.HiddSec, self.TotSec32, self.FATSz32 = \
        struct.unpack('<3s8sHBHBHHBHHHLLL', block0[:40])

        # Calculate the number of sectors occupied by the root directory.
        self.RootDirSectors = int(
            (self.RootEntCnt * 32 + self.BytsPerSec - 1) /
            self.BytsPerSec)

        # Calculate the first data sector in the FAT image file.
        self.FirstDataSector = self.ResvdSecCnt + (
            self.NumFATs * self.FATSz16) + self.RootDirSectors

        # Calculate the number of data sectors in the FAT image file.
        self.DataSec = self.TotSec16 - (self.ResvdSecCnt +
                                         (self.NumFATs * self.FATSz16) + self.RootDirSectors)

        # Calculate the total number of clusters in the FAT image file.
        self.CountOfClusters = int(self.DataSec / self.SecPerClus)

        # Set the starting sector number of the first FAT table.
        self.FATStart = self.ResvdSecCnt

        # Set the starting sector number of the root directory.
        self.RootDirStart = self.ResvdSecCnt + self.NumFATs * self.FATSz16
        self.seen_clusters = set()

    def find_unlinked_files(self):
    # This method searches for unlinked files in the FAT filesystem and saves them to a directory called "Unlinked".

    # Create the "Unlinked" directory if it does not exist.
        os.makedirs("unlinked", exist_ok=True)

        # Iterate through all clusters in the filesystem.
        for cluster in range(2, self.CountOfClusters):
            if cluster in self.seen_clusters:
                continue
            # Read the next cluster entry in the FAT table.
            next_cluster = self.read_fat_entry(cluster)

            # Check if the cluster is allocated (not free or reserved).
            if 0x002 <= next_cluster <= 0xFEF:

                # Initialize an empty bytes object to store the content of the unlinked file.
                file_data = b''
                # Set the current cluster to the cluster we are examining.
                current_cluster = cluster
                # Continue reading until the end-of-chain marker is reached (0xFFF0).
                while current_cluster < 0xFFF8:
                    
                    # Calculate the sector number corresponding to the current cluster.
                    current_sector = self.FirstDataSector + (current_cluster - 2) * self.SecPerClus
                    # Iterate through all sectors in the current cluster and read their data.
                    for i in range(self.SecPerClus):
                        file_data += self.getSector(current_sector + i)
                    # Read the next cluster entry in the FAT table.
                    current_cluster = self.read_fat_entry(current_cluster)
                    self.seen_clusters.add(current_cluster)

                # Save the content of the unlinked file to a file named "unlinked_file_{cluster}.txt" in the "Unlinked" directory.
                with open(f"unlinked/unlinked_file_{cluster}.txt", "wb") as output_file:
                    output_file.write(file_data)
                
                # Save the content of the unlinked file to a file named "unlinked_file_{cluster}.bin" in the "Unlinked" directory.
                with open(f"unlinked/unlinked_file_{cluster}.bin", "wb") as output_file:
                    output_file.write(file_data)


    def find_file_data(self):
    # This method attempts to recover data from files within the filesystem.
    
    # Read the data from the root directory.
        root_dir_data = self.getSector(self.RootDirStart)

        # Check if the root directory is empty.
        is_root_empty = all(byte == 0 for byte in root_dir_data)

        if is_root_empty:
            # Initialize a file counter.
            file_counter = 1
            # Create a directory called "Recovered_files" if it does not exist.
            os.makedirs("Recovered_files", exist_ok=True)

            # Initialize a list to store the information of the recovered files.
            good_files = []

            # Open a listing file to store the details of the recovered files.
            with open("listing.txt", "w") as listing_file:
                # Iterate through all clusters in the filesystem.
                for cluster in range(2, self.CountOfClusters):
                    # Calculate the starting sector of the current cluster.
                    start_sector = self.FirstDataSector + \
                        (cluster - 2) * self.SecPerClus
                    # Read the data from the starting sector.
                    sector_data = self.getSector(start_sector)

                    # Check if the current sector data indicates a potential directory.
                    if sector_data[0] == 0x2E and sector_data[11] == 0x10:

                        # Calculate the starting sector of the potential directory.
                        dir_start_sector = self.FirstDataSector + \
                            (cluster - 2) * self.SecPerClus

                        # Initialize an empty bytes object to store the data from the directory cluster.
                        cluster_data = b''
                        # Read the data from all sectors in the directory cluster.
                        for i in range(self.SecPerClus):
                            cluster_data += self.getSector(dir_start_sector + i)
                        # Assign the cluster data to dir_data.
                        dir_data = cluster_data
                        # Write information about the found directory to the listing file.
                        listing_file.write(f"Directory at cluster {cluster}:\n")

                        # Iterate through the directory entries in 32-byte increments.
                        for i in range(0, len(dir_data), 32):
                            # Extract the current directory entry data.
                            entry_data = dir_data[i:i+32]
                            # Check if the entry is empty or deleted.
                            if entry_data[0] in (0x00, 0xE5):
                                continue  # Skip the current entry.
                            # Check if the current entry is not a directory.
                            if entry_data[11] != 0x10:
                                # Generate a file name using the file counter.
                                file_name = f"FILE{file_counter:04}"
                                # Extract the file name and extension from the entry data.
                                file_name_listing = struct.unpack("<8s3s", entry_data[:11])
                                # Extract the starting cluster and file size from the entry data.
                                starting_cluster = struct.unpack("<H", entry_data[26:28])[0]
                                file_size = struct.unpack("<L", entry_data[28:32])[0]

                                # Check if the entry represents a regular file.
                                if entry_data[11] == 0x20:
                                    # Increment the file counter.
                                    file_counter += 1
                                    # Write information about the good file to the listing file.
                                    listing_file.write(f"Good file: {file_name_listing[0].decode('ascii').strip()} - Length: {file_size}\n")
                                    # Initialize an empty bytes object to store the content of the good file.
                                    file_data = b''
                                    # Set the current cluster to the starting cluster.
                                    current_cluster = starting_cluster
                                    # Read the content of the good file until the end-of-chain marker is reached.
                                    while current_cluster < 0xFFF0:
                                        # Calculate the current sector based on the current cluster.
                                        current_sector = self.FirstDataSector + (current_cluster - 2) * self.SecPerClus
                                        # Read data from all sectors in the current cluster.
                                        for i in range(self.SecPerClus):
                                            file_data += self.getSector(current_sector + i)
                                        self.seen_clusters.add(current_cluster)
                                        # Update the current cluster by reading the FAT entry.
                                        current_cluster = self.read_fat_entry(current_cluster)
                                    # Truncate the file data to its actual size.
                                    file_data = file_data[:file_size]
                                    # Save the file data to a text file in the "Recovered_files" directory.
                                    with open(f"Recovered_files/{file_name}.txt", "wb") as output_file:
                                        output_file.write(file_data)
                                    # Save the file data to a binary file in the "Recovered_files" directory.
                                    with open(f"Recovered_files/{file_name}.bin", "wb") as bin_file:
                                        bin_file.write(file_data)
                                    # Add the file information to the good_files list.
                                    good_files.append((file_name_listing, file_data))
                                else:
                                    # If the entry does not represent a regular file, set the file type to "bad".
                                    file_type = "bad"

                        # Write a newline to the listing file after processing the current directory.
                        listing_file.write("\n")

            # Return the list of good files.
            return good_files

    def close(self) -> None:
        # This method closes the FAT file.
        self.fatFile.close()

def create_good_files_directory(good_files):
    # Create the "Good_Files" directory if it doesn't already exist.
    os.makedirs("Good_Files", exist_ok=True)
    # Copy the "listing.txt" file to the "Good_Files" directory.
    shutil.copy("listing.txt", "Good_Files/listing.txt")

    # Iterate through the list of good files and their data.
    for file_name_listing, file_data in good_files:
        # Create the complete file name using the file name and extension from the listing.
        file_name = f"{file_name_listing[0].decode('ascii').strip()}.{file_name_listing[1].decode('ascii').strip()}"
        # Write the file data to the "Good_Files" directory.
        with open(f"Good_Files/{file_name}", "wb") as output_file:
            output_file.write(file_data)

if __name__ == "__main__":
    # Define the FAT16 image file name.
    image_file = "fat16-36169241-36.img"
    # Create an instance of the FAT class with the specified image file.
    fat = FAT(image_file)
    # Call the find_file_data method to recover good files and their data.
    good_files = fat.find_file_data()
    # Call the find_unlinked_files method to recover unlinked files.
    fat.find_unlinked_files()
    # Call the create_good_files_directory method to create a directory with the recovered good files.
    create_good_files_directory(good_files)
    # Close the FAT file.
    fat.close()



